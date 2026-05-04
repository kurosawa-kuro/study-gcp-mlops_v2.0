"""Parity: ``scripts.setup.destroy_all.PROTECTED_TARGETS`` ↔ Terraform sources.

``destroy-all`` の step ``[4/6]`` は **server-side** ``deletion_protection`` を
持つリソースに対して `terraform apply -var=enable_deletion_protection=false
-target=<each>` を打って attribute を server-side で flip してから本体 destroy
に進む。`PROTECTED_TARGETS` (旧 `PROTECTED_TABLE_TARGETS`) が destroy 対象と
ズレると本体 destroy が `Error: cannot destroy ... deletion_protection=true`
で fail する (Phase 6 Run 2 で BQ table 2 件、Phase 7 Run 4 で GKE cluster で
発症済の事故パターン)。

このテストは:
- BQ table 群 ↔ ``infra/terraform/modules/data/main.tf`` の lockstep
- GKE cluster ↔ ``infra/terraform/modules/gke/main.tf`` の lockstep
- baseline 件数の sanity check
を pin して drift を CI で捕捉する。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_TF = REPO_ROOT / "infra" / "terraform" / "modules" / "data" / "main.tf"
GKE_TF = REPO_ROOT / "infra" / "terraform" / "modules" / "gke" / "main.tf"

_BQ_TABLE_RE = re.compile(r'resource\s+"google_bigquery_table"\s+"([^"]+)"')
_GKE_CLUSTER_RE = re.compile(r'resource\s+"google_container_cluster"\s+"([^"]+)"')
_PROTECTED_RE = re.compile(r"deletion_protection\s*=\s*(?:true|var\.\w+)")

BQ_TABLE_PREFIX = "module.data.google_bigquery_table."
GKE_CLUSTER_PREFIX = "module.gke.google_container_cluster."


def _resources_with_deletion_protection(tf_file: Path, resource_re: re.Pattern[str]) -> set[str]:
    """Return resource names whose body references ``deletion_protection``
    (either literal ``true`` or bound to a Terraform variable).

    Brace-balanced split is overkill for current tf files; the split-by-
    ``resource "..." "..."`` approach works because resource blocks don't
    nest at the top level.
    """
    text = tf_file.read_text(encoding="utf-8")
    found: set[str] = set()
    blocks = re.split(r'(?=resource\s+"[^"]+"\s+"[^"]+"\s*\{)', text)
    for block in blocks:
        m = resource_re.match(block)
        if not m:
            continue
        if _PROTECTED_RE.search(block):
            found.add(m.group(1))
    return found


def _destroy_all_targets() -> list[str]:
    from scripts.setup.destroy_all import PROTECTED_TARGETS

    return list(PROTECTED_TARGETS)


def _destroy_bq_table_names() -> set[str]:
    return {
        target[len(BQ_TABLE_PREFIX) :]
        for target in _destroy_all_targets()
        if target.startswith(BQ_TABLE_PREFIX)
    }


def _destroy_gke_cluster_names() -> set[str]:
    return {
        target[len(GKE_CLUSTER_PREFIX) :]
        for target in _destroy_all_targets()
        if target.startswith(GKE_CLUSTER_PREFIX)
    }


def test_every_protected_bq_table_is_in_destroy_all_targets() -> None:
    """Every BQ table with ``deletion_protection`` in data/main.tf must be
    listed in ``PROTECTED_TARGETS``; otherwise step ``[4/6]`` skips the
    flip and step ``[6/6]`` body destroy fails on that table.
    """
    tf_tables = _resources_with_deletion_protection(DATA_TF, _BQ_TABLE_RE)
    destroy_tables = _destroy_bq_table_names()
    missing = tf_tables - destroy_tables
    assert not missing, (
        f"New protected BQ table(s) in data/main.tf not mirrored into "
        f"PROTECTED_TARGETS: {sorted(missing)}. Add them prefixed with "
        f"`{BQ_TABLE_PREFIX}` before merging."
    )


def test_destroy_all_bq_targets_do_not_reference_removed_tables() -> None:
    """Opposite drift: a table removed from data/main.tf must not linger in
    PROTECTED_TARGETS — otherwise the state-flip apply fails with
    ``resource not in state``.
    """
    tf_tables = _resources_with_deletion_protection(DATA_TF, _BQ_TABLE_RE)
    destroy_tables = _destroy_bq_table_names()
    stale = destroy_tables - tf_tables
    assert not stale, (
        f"PROTECTED_TARGETS references BQ tables not in data/main.tf: "
        f"{sorted(stale)}. Remove them from destroy_all.py."
    )


def test_protected_gke_cluster_is_in_destroy_all_targets() -> None:
    """The GKE cluster `deletion_protection` is wired through
    `var.deletion_protection` in modules/gke/main.tf. Without flipping it
    server-side first the body destroy fails with
    ``Cannot destroy cluster because deletion_protection is set to true``
    (Phase 7 Run 4 incident).
    """
    tf_clusters = _resources_with_deletion_protection(GKE_TF, _GKE_CLUSTER_RE)
    destroy_clusters = _destroy_gke_cluster_names()
    missing = tf_clusters - destroy_clusters
    assert not missing, (
        f"GKE cluster(s) with deletion_protection in modules/gke/main.tf "
        f"not mirrored into PROTECTED_TARGETS: {sorted(missing)}. "
        f"Add them prefixed with `{GKE_CLUSTER_PREFIX}`."
    )


def test_protected_targets_baseline() -> None:
    """Sanity: Phase 7 baseline = 10 BQ tables + 1 GKE cluster = 11.
    Bump this when adding any new protected resource so future readers see
    the canonical baseline.
    """
    targets = _destroy_all_targets()
    assert len(targets) == 11, (
        f"Expected 11 protected resources (10 BQ tables + 1 GKE cluster, "
        f"Phase 7 baseline), got {len(targets)}: {sorted(targets)}. "
        "If the count changed intentionally, bump this baseline."
    )
