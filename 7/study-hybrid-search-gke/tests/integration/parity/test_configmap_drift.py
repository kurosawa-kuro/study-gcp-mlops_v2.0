"""Drift detection: ``configmap.example.yaml`` must equal the
``scripts/ci/sync_configmap.render()`` output, AND the generator schema
must cover every key referenced from ``deployment.yaml``.

The committed file is the **canonical artifact** (operators copy +
overlay it before applying). Drift between the committed file and what
``render()`` would produce from ``env/config/setting.yaml`` means either:

1. Someone hand-edited the committed YAML without bumping setting.yaml
   (the file says "AUTO-GENERATED — do NOT edit by hand").
2. ``setting.yaml::project_id`` was bumped without rerunning
   ``make sync-configmap``.

Either way, ``make apply-manifests`` will deploy a stale ConfigMap. CI
fails fast here so the diff surfaces in the PR.

Also asserts that ``scripts/lib/config.CONFIGMAP_KEYS`` covers every key
referenced via ``configMapKeyRef`` in ``infra/manifests/search-api/deployment.yaml``.
W2-5 で deployment.yaml が新キーを参照するのに deploy_all overlay が古い
キー列のままだったため Pod が ``CreateContainerConfigError`` で起動失敗した
事故への構造的対策。「deployment が参照する全キーを generator が出力する」
ことを保証する。
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.ci.sync_configmap import OUTPUT, render
from scripts.lib.config import CONFIGMAP_KEYS

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOYMENT_YAML = REPO_ROOT / "infra" / "manifests" / "search-api" / "deployment.yaml"


def test_committed_configmap_matches_generator_output() -> None:
    committed = OUTPUT.read_text(encoding="utf-8")
    expected = render()
    assert committed == expected, (
        "configmap.example.yaml drifts from setting.yaml. "
        "Run `make sync-configmap` and commit the result."
    )


def test_configmap_keys_cover_every_deployment_reference() -> None:
    """Every ``configMapKeyRef.key`` in deployment.yaml must exist in CONFIGMAP_KEYS.

    This is the structural safeguard against the Phase 7 W2-5 incident
    where deployment.yaml bound 7 new keys (semantic_backend / vertex_*_*)
    but the deploy_all overlay kept the old 3-key schema, blocking
    rollout with ``CreateContainerConfigError``. Now that
    ``scripts/lib/config.py`` is the single source for both
    sync_configmap and deploy/configmap_overlay, this test ensures any
    future addition of a ``configMapKeyRef`` is matched by an addition
    to CONFIGMAP_KEYS.
    """
    text = DEPLOYMENT_YAML.read_text(encoding="utf-8")
    # Match `configMapKeyRef:\n  name: search-api-config\n  key: <name>`
    # (also tolerate trailing whitespace and the inverse field order).
    refs: set[str] = set()
    for match in re.finditer(
        r"configMapKeyRef:\s*(?:[^\n]*\n)+?\s*key:\s*(\w+)",
        text,
    ):
        refs.add(match.group(1))
    assert refs, (
        "deployment.yaml had no configMapKeyRef entries — the regex must "
        "have stopped matching the manifest layout. Re-check this test."
    )
    missing = refs - set(CONFIGMAP_KEYS)
    assert not missing, (
        "deployment.yaml references ConfigMap keys that the generator does "
        f"not emit: {sorted(missing)}. Add them to "
        "scripts/lib/config.py::_GROUPS / _DEFAULTS so both sync_configmap "
        "and deploy_all overlay stay in lockstep (W2-5 type fix)."
    )


def test_generated_configmap_keeps_deployment_referenced_keys() -> None:
    """The generated YAML must still expose every key Deployment references.

    ``test_manifests_structure.py::test_configmap_example_covers_expected_keys``
    asserts the same against the committed file, but if a future change
    drops a generator key the manifest test would only catch it after
    ``make sync-configmap`` runs. This pins the generator output directly
    so the regression surfaces even before the committed file updates.
    """
    rendered = render()
    for required in (
        "project_id:",
        "models_bucket:",
        "meili_base_url:",
        "vertex_vector_search_index_endpoint_id:",
        "vertex_vector_search_deployed_index_id:",
        "vertex_feature_online_store_id:",
        "vertex_feature_view_id:",
        "vertex_feature_online_store_endpoint:",
    ):
        assert required in rendered, f"sync_configmap.render() dropped required key: {required!r}"
