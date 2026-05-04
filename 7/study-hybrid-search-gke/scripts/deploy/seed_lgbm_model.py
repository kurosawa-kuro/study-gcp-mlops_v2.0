"""Seed a synthetic LightGBM LambdaRank model so the KServe reranker
InferenceService has a valid ``storageUri`` artifact on the first
``deploy-all`` of a fresh project.

Why this exists (Phase 7 Run 1 incident): a freshly-applied
``infra/manifests/kserve/reranker.yaml`` references
``gs://${PROJECT_ID}-models/lgbm/latest`` as ``spec.predictor.model.storageUri``.
The KServe storage-initializer init-container scans that prefix at Pod start
and refuses to come up with::

    RuntimeError: Failed to fetch model. No model found in
    gs://mlops-dev-a-models/lgbm/latest.

Until the Vertex AI training pipeline produces a real LightGBM artifact
(``rank-train`` → upload to Model Registry → ``deploy-kserve-models``),
the reranker Pod stays in ``Init:Error`` and ``/search`` returns 500.
That blocks the whole E2E smoke test.

This script bootstraps a synthetic ``model.bst`` (byte-identical to a real
``model.txt`` since LightGBM's text format works for both formats — see
``ml/training/trainer.py::write_artifacts``) so the reranker starts. Once
real training succeeds, the production alias path overwrites this seed.

Idempotency: if ``gs://.../lgbm/latest/model.bst`` already exists with
non-zero size, this script logs and exits 0 without touching it. That keeps
``make deploy-all`` re-runs cheap and avoids overwriting a real model with
synthetic one if the caller forgets which step they ran.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from scripts._common import env, gcloud, gcs_bucket_name, run

DEFAULT_BUCKET_SUFFIX = (
    "models"  # `<project>-models`; see scripts.lib.gcp_resources.BUCKET_SUFFIXES
)
DEFAULT_PREFIX = "lgbm/latest"
MODEL_FILENAME = "model.bst"


def _step(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def _info(msg: str) -> None:
    print(f"[info] {msg}", flush=True)


def _resolve_bucket() -> str:
    explicit = env("MODELS_BUCKET")
    if explicit:
        return explicit
    if not env("PROJECT_ID"):
        raise SystemExit("[error] PROJECT_ID is empty and MODELS_BUCKET is not set")
    return gcs_bucket_name(DEFAULT_BUCKET_SUFFIX)


def _existing_object_size(gs_uri: str) -> int:
    """Return blob size in bytes, or -1 if missing/unreachable."""
    proc = subprocess.run(
        [
            "gcloud",
            "storage",
            "objects",
            "describe",
            gs_uri,
            "--format=value(size)",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        return -1
    raw = (proc.stdout or "").strip()
    if not raw:
        return -1
    try:
        return int(raw)
    except ValueError:
        return -1


def _train_synthetic_model(target: Path) -> None:
    """Run ``rank-train --dry-run --save-to <target>`` to produce a smoke model.

    ``rank-train`` is the entry point exposed by ``ml.training.cli`` (see
    ``pyproject.toml``). The dry-run path uses synthetic LambdaRank data
    so this works without GCS / BQ access during builds.
    """
    _step(f"rank-train --dry-run --save-to {target}")
    run(
        ["uv", "run", "rank-train", "--dry-run", "--save-to", str(target)],
        check=True,
    )
    if not target.exists():
        raise SystemExit(
            f"[error] rank-train --dry-run did not produce {target} — "
            "check ml.training.trainer logs above"
        )
    _info(f"synthetic model written ({target.stat().st_size} bytes)")


def _upload(local_path: Path, gs_uri: str) -> None:
    _step(f"gcloud storage cp {local_path} {gs_uri}")
    gcloud("storage", "cp", str(local_path), gs_uri)


def main() -> int:
    bucket = _resolve_bucket()
    prefix = env("LGBM_MODEL_PREFIX") or DEFAULT_PREFIX
    target_uri = f"gs://{bucket}/{prefix.rstrip('/')}/{MODEL_FILENAME}"

    _step(f"seed-lgbm-model start target={target_uri}")

    existing_size = _existing_object_size(target_uri)
    if existing_size > 0:
        _info(
            f"target already exists ({existing_size} bytes) — skip "
            "(set FORCE_RESEED=1 to overwrite)"
        )
        if env("FORCE_RESEED") not in {"1", "true", "yes", "on"}:
            return 0

    with tempfile.TemporaryDirectory(prefix="seed-lgbm-") as tmp:
        local_model = Path(tmp) / MODEL_FILENAME
        _train_synthetic_model(local_model)
        _upload(local_model, target_uri)

    _step(f"seed-lgbm-model DONE target={target_uri}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
