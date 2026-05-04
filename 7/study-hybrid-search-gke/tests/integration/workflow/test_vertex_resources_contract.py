"""Phase 7 workflow contract — Vertex Vector Search / Feature Online Store /
legacy serverless trigger 格下げ.

Pin VVS deployed_index_id versioning + replica bound + FOS Feature View source
+ Cloud Scheduler / Cloud Function / Eventarc / `/jobs/check-retrain` の
smoke 格下げ済 wording。
"""

from __future__ import annotations

import re

from tests.integration.workflow.conftest import read_repo_file as _read


def test_vvs_module_lifecycle_protects_against_stale_id_recreation() -> None:
    """`deployed_index_id` は v3+ (v1 / v2 ともに soft-state grace period に焼かれた)。"""
    variables_tf = _read("infra/terraform/modules/vector_search/variables.tf")
    match = re.search(
        r'variable "deployed_index_id"[^}]*default\s*=\s*"([^"]+)"',
        variables_tf,
        flags=re.DOTALL,
    )
    assert match is not None
    deployed_id = match.group(1)
    version_match = re.search(r"_v(\d+)$", deployed_id)
    assert version_match is not None, (
        f"deployed_index_id {deployed_id!r} must end with _vN versioned suffix"
    )
    version = int(version_match.group(1))
    assert version >= 3, (
        f"deployed_index_id version {version} must be >=3 "
        "(v1 burned 2026-05-02; v2 burned 2026-05-03 — both by GCP soft-state grace period)"
    )


def test_vvs_module_min_max_replica_pinned_to_one_for_dev() -> None:
    """VVS deployed index `min = max = 1` で dev コスト + provisioning 時間を bound。"""
    main_tf = _read("infra/terraform/modules/vector_search/main.tf")
    variables_tf = _read("infra/terraform/modules/vector_search/variables.tf")

    min_match = re.search(
        r'variable "min_replica_count"[^}]*default\s*=\s*(\d+)',
        variables_tf,
        flags=re.DOTALL,
    )
    max_match = re.search(
        r'variable "max_replica_count"[^}]*default\s*=\s*(\d+)',
        variables_tf,
        flags=re.DOTALL,
    )
    assert min_match is not None and max_match is not None
    assert int(min_match.group(1)) == 1
    assert int(max_match.group(1)) == 1
    assert "min_replica_count" in main_tf and "max_replica_count" in main_tf


def test_feature_view_online_serving_source_is_direct_bigquery() -> None:
    """Feature View が BigQuery `property_features_online_latest` を直接参照する契約。"""
    data_tf = _read("infra/terraform/modules/data/main.tf")
    vertex_tf = _read("infra/terraform/modules/vertex/main.tf")
    deploy_all_py = _read("scripts/setup/deploy_all.py")
    stage_apply_py = _read("scripts/infra/terraform_stage_apply.py")
    assert 'table_id            = "property_features_online_latest"' in data_tf
    assert "depends_on          = [google_bigquery_table.property_features_daily]" in data_tf
    assert (
        "FROM `${var.project_id}.${google_bigquery_dataset.feature_mart.dataset_id}.property_features_daily`"
        in data_tf
    )
    assert 'WHERE event_date = CURRENT_DATE("Asia/Tokyo")' in data_tf
    assert (
        'uri = "bq://${var.project_id}.${var.feature_mart_dataset_id}.property_features_online_latest"'
        in vertex_tf
    )
    assert 'entity_id_columns = ["property_id"]' in vertex_tf
    assert "feature_registry_source {" not in vertex_tf
    assert "TF_APPLY_STAGE1_TARGETS" in stage_apply_py
    assert "wait_for_deployed_index_absent" in deploy_all_py
    assert "wait_until_api_ready" in deploy_all_py


def test_legacy_cloud_scheduler_demoted_to_monthly_smoke() -> None:
    """Stage 3.2 格下げ契約: `check-retrain-daily` を `0 4 * * *` →
    `0 4 1 * *` (monthly smoke) に。本線 retrain は Composer DAG。"""
    messaging_tf = _read("infra/terraform/modules/messaging/main.tf")
    assert 'schedule    = "0 4 1 * *"' in messaging_tf
    assert "smoke" in messaging_tf


def test_legacy_cloud_function_eventarc_marked_as_smoke() -> None:
    """Stage 3.2: Cloud Function `pipeline_trigger` + Eventarc 2 本に
    「smoke / 軽量代替経路として残置」コメントが記載されていること。"""
    vertex_tf = _read("infra/terraform/modules/vertex/main.tf")
    assert "Stage 3 で smoke" in vertex_tf or "軽量代替経路として残置" in vertex_tf


def test_retrain_router_marked_as_smoke_endpoint() -> None:
    """Stage 3.2: `app/api/routers/retrain_router.py` docstring に
    「本線スケジューラから格下げ」「Composer DAG が呼ぶ smoke 経路」明記契約。"""
    router_py = _read("app/api/routers/retrain_router.py")
    assert "本線スケジューラから格下げ" in router_py
    assert "Composer DAG" in router_py
