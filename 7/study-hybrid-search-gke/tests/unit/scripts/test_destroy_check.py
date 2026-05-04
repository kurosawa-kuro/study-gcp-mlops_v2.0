from __future__ import annotations

from scripts.ops import destroy_check


def test_classify_bucket_names_splits_fail_and_warn() -> None:
    fail_items, warn_items = destroy_check._classify_bucket_names(
        "mlops-dev-a",
        (
            "mlops-dev-a-models",
            "mlops-dev-a-pipeline-root",
            "mlops-dev-a-tfstate",
            "mlops-dev-a-vertex",
            "gcf-v2-sources-941178142366-asia-northeast1",
            "cloud-ai-platform-b4a68fac-565b-42db-89d6-a9a835c1baea",
        ),
    )

    assert fail_items == ("mlops-dev-a-models", "mlops-dev-a-pipeline-root")
    assert warn_items == (
        "cloud-ai-platform-b4a68fac-565b-42db-89d6-a9a835c1baea",
        "gcf-v2-sources-941178142366-asia-northeast1",
        "mlops-dev-a-tfstate",
        "mlops-dev-a-vertex",
    )


def test_classify_artifact_repos_splits_google_managed_repo() -> None:
    fail_items, warn_items = destroy_check._classify_artifact_repos(("gcf-artifacts", "mlops"))

    assert fail_items == ("mlops",)
    assert warn_items == ("gcf-artifacts",)


def test_filter_high_cost_datasets_ignores_unrelated_datasets() -> None:
    assert destroy_check._filter_high_cost_datasets(
        ("feature_mart", "misc", "mlops", "predictions")
    ) == ("feature_mart", "mlops", "predictions")


def test_looks_like_api_disabled_detects_disabled_service_errors() -> None:
    assert destroy_check._looks_like_api_disabled(
        "PERMISSION_DENIED: API [run.googleapis.com] has not been used in project"
    )
    assert not destroy_check._looks_like_api_disabled("permission denied for caller")
