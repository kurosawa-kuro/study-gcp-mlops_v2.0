"""Structural sanity checks for the GitHub Actions workflows.

This is not a YAML schema validator — it only enforces the few invariants that
keep the deploy pipeline coherent with the repo layout:

* every deploy workflow specifies ``id-token: write`` (required for WIF OIDC),
* the Vertex CPR image workflows point at the right Dockerfile / path filter
  so they fire when the server code they ship changes,
* deploy-api keeps the broad ``app/**`` + ``ml/**`` filter and injects the
  Vertex Endpoint env vars consumed by ``app/main.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

REQUIRED_WORKFLOWS = (
    "ci.yml",
    "deploy-api.yml",
    "deploy-dataform.yml",
    "deploy-encoder-image.yml",
    "deploy-reranker-image.yml",
    "deploy-trainer-image.yml",
    "deploy-pipeline.yml",
    "terraform.yml",
)

RETIRED_WORKFLOWS = (
    "deploy-training-job.yml",
    "deploy-embedding-job.yml",
)


@pytest.mark.parametrize("filename", REQUIRED_WORKFLOWS)
def test_workflow_file_exists(filename: str) -> None:
    assert (WORKFLOWS_DIR / filename).is_file(), (
        f"missing .github/workflows/{filename} — required by the CI/CD matrix"
    )


@pytest.mark.parametrize("filename", RETIRED_WORKFLOWS)
def test_retired_workflows_are_absent(filename: str) -> None:
    """Phase 9 deleted the Cloud Run Jobs `training-job` / `embedding-job`.

    The two legacy workflows should no longer exist; KFP pipelines replace them.
    """
    assert not (WORKFLOWS_DIR / filename).exists(), (
        f"{filename} must be removed — replaced by KFP pipelines in Phase 9"
    )


@pytest.mark.parametrize(
    "filename",
    [
        "deploy-api.yml",
        "deploy-encoder-image.yml",
        "deploy-reranker-image.yml",
        "deploy-trainer-image.yml",
        "deploy-pipeline.yml",
        "terraform.yml",
    ],
)
def test_deploy_workflows_request_oidc_token(filename: str) -> None:
    text = (WORKFLOWS_DIR / filename).read_text()
    assert "id-token: write" in text, (
        f"{filename} must request id-token:write permission for Workload Identity Federation"
    )


def test_encoder_image_workflow_paths() -> None:
    text = (WORKFLOWS_DIR / "deploy-encoder-image.yml").read_text()
    assert "infra/run/services/encoder/Dockerfile" in text
    assert "ml/serving/**" in text


def test_reranker_image_workflow_paths() -> None:
    text = (WORKFLOWS_DIR / "deploy-reranker-image.yml").read_text()
    assert "infra/run/services/reranker/Dockerfile" in text
    assert "ml/serving/**" in text


def test_trainer_image_workflow_paths() -> None:
    text = (WORKFLOWS_DIR / "deploy-trainer-image.yml").read_text()
    assert "infra/run/jobs/training/Dockerfile" in text
    assert "ml/training/**" in text


def test_pipeline_workflow_paths() -> None:
    text = (WORKFLOWS_DIR / "deploy-pipeline.yml").read_text()
    assert "pipeline/data_job/**" in text
    assert "pipeline/training_job/**" in text
    assert "pipeline/workflow/**" in text
    assert "setup_model_monitoring" in text
    assert "create_schedule" in text


def test_api_workflow_keeps_broad_filter_and_rolls_out_via_kubectl() -> None:
    """Phase 7 deploy-api.yml contract.

    The workflow triggers on ``app/**`` and ``ml/**`` changes, then rolls the
    new image via ``kubectl set image`` + ``kubectl rollout status`` (not
    ``gcloud run deploy``). Phase 5/6 Vertex env injection moved out of the
    deploy-api workflow — the Deployment ConfigMap (infra/manifests/search-api)
    owns KSERVE_* URLs now, and Vertex endpoint IDs are no longer needed
    because encoder/reranker live on KServe instead of Vertex Endpoints.
    """
    text = (WORKFLOWS_DIR / "deploy-api.yml").read_text()
    assert "- app/**" in text
    assert "- ml/**" in text
    assert "kubectl set image" in text, (
        "Phase 7 rolls search-api via `kubectl set image`, not `gcloud run deploy`."
    )
    assert "deployment/" in text, (
        "`kubectl set image deployment/<name>` is the Phase 7 rollout target."
    )
    assert "rollout status" in text, (
        "`kubectl rollout status` must gate the CI step on successful rollout."
    )
