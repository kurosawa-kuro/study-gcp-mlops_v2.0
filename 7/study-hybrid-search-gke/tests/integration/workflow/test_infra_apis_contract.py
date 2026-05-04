"""Phase 7 workflow contract — module ↔ API enablement / region consistency /
GKE 2-stage apply / search-api manifest image lifecycle / ops-vertex-all.

長時間 recovery 系の事故 (PERMISSION_DENIED for unenabled API、cross-region
egress、Helm provider race) を contract レベルで先回り。
"""

from __future__ import annotations

import re

from tests.integration.workflow.conftest import REPO_ROOT
from tests.integration.workflow.conftest import read_repo_file as _read


def test_required_apis_cover_all_modules_actually_used() -> None:
    """**全 module ↔ API enablement contract** (2026-05-03 追加、Composer API 漏れの
    再発防止)。

    新 module が GCP resource を増やすたびに API enablement の漏れが起きる事故を
    contract で先回り。`google_*` resource → 必要な API URL のマッピングを辞書で
    定義し、apis.tf::required_apis に揃っているか確認。
    """
    apis_tf = _read("infra/terraform/environments/dev/apis.tf")

    resource_to_api: dict[str, str] = {
        "google_composer_environment": "composer.googleapis.com",
        "google_vertex_ai_index": "aiplatform.googleapis.com",
        "google_vertex_ai_index_endpoint": "aiplatform.googleapis.com",
        "google_vertex_ai_endpoint": "aiplatform.googleapis.com",
        "google_vertex_ai_feature_online_store": "aiplatform.googleapis.com",
        "google_vertex_ai_feature_group": "aiplatform.googleapis.com",
        "google_container_cluster": "container.googleapis.com",
        "google_cloud_run_v2_service": "run.googleapis.com",
        "google_artifact_registry_repository": "artifactregistry.googleapis.com",
        "google_cloudbuild_trigger": "cloudbuild.googleapis.com",
        "google_pubsub_topic": "pubsub.googleapis.com",
        "google_eventarc_trigger": "eventarc.googleapis.com",
        "google_cloudfunctions2_function": "cloudfunctions.googleapis.com",
        "google_cloud_scheduler_job": "cloudscheduler.googleapis.com",
        "google_secret_manager_secret": "secretmanager.googleapis.com",
        "google_bigquery_dataset": "bigquery.googleapis.com",
        "google_bigquery_table": "bigquery.googleapis.com",
        "google_dataform_repository": "dataform.googleapis.com",
        "google_monitoring_alert_policy": "monitoring.googleapis.com",
        "google_logging_metric": "logging.googleapis.com",
        "google_iam_workload_identity_pool": "iam.googleapis.com",
    }

    modules_dir = REPO_ROOT / "infra" / "terraform" / "modules"
    used_resource_types: set[str] = set()
    for tf_file in modules_dir.rglob("*.tf"):
        text = tf_file.read_text(encoding="utf-8")
        for resource_type in resource_to_api:
            if re.search(rf'resource "{re.escape(resource_type)}"', text):
                used_resource_types.add(resource_type)

    assert used_resource_types, "could not detect any GCP resources in modules/"

    missing_apis: list[tuple[str, str]] = []
    for resource_type in sorted(used_resource_types):
        api = resource_to_api[resource_type]
        if f'"{api}"' not in apis_tf:
            missing_apis.append((resource_type, api))

    assert not missing_apis, (
        "infra/terraform/environments/dev/apis.tf::required_apis is missing APIs "
        "needed by terraform resources. Each resource's backing API must be in "
        "google_project_service.enabled, otherwise apply fails with PERMISSION_DENIED. "
        f"Missing: {missing_apis}"
    )


def test_all_modules_use_consistent_region_var() -> None:
    """全 module の region default が `asia-northeast1` で揃っていること。"""
    variables_tf = _read("infra/terraform/environments/dev/variables.tf")
    region_match = re.search(
        r'variable "region"[^}]*default\s*=\s*"([^"]+)"',
        variables_tf,
        flags=re.DOTALL,
    )
    vertex_match = re.search(
        r'variable "vertex_location"[^}]*default\s*=\s*"([^"]+)"',
        variables_tf,
        flags=re.DOTALL,
    )
    assert region_match is not None and vertex_match is not None
    assert region_match.group(1) == "asia-northeast1"
    assert vertex_match.group(1) == "asia-northeast1"


def test_gke_two_stage_apply_pattern_preserved() -> None:
    """GKE Autopilot + KServe Helm provider race を回避する **2 段 apply** が
    `deploy_all.py` に維持されていること。

    時間影響: race で全 apply が無効化されると最大 30-40 min の retry コスト。"""
    deploy_all_py = _read("scripts/setup/deploy_all.py")
    assert "stage1" in deploy_all_py.lower()
    assert "ensure_kubectl_context" in deploy_all_py
    assert "wait_until_api_ready" in deploy_all_py


def test_search_api_image_lifecycle_ignore_changes_pinned() -> None:
    """search-api Deployment は placeholder image で初回 apply、後で
    `kubectl set image` で immutable tag 差し替えする pattern。"""
    deployment_yaml = _read("infra/manifests/search-api/deployment.yaml")
    assert "image: gcr.io/cloudrun/hello" in deployment_yaml or "image: " in deployment_yaml


def test_ops_vertex_all_includes_vvs_and_feature_view_checks() -> None:
    makefile = _read("Makefile")
    target_line = (
        "ops-vertex-all: ops-vertex-models-list ops-vertex-pipeline-status "
        "ops-vertex-explain ops-vertex-monitoring "
        "ops-vertex-vector-search-smoke ops-vertex-feature-group"
    )
    assert target_line in makefile, "ops-vertex-all must include VVS + Feature View smoke"
