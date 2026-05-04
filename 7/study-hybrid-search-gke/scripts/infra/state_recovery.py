"""Generic GCP resource state recovery — import existing GCP resources into tfstate.

**背景** (2026-05-03 incident postmortem):
- `runbook §1.4-emergency` の「緊急 cleanup 後の tfstate orphan cleanup」で、
  state list 全件を `state rm` で消すレシピがあった
- これは GCP 側で **本当に消えた resources** のための clean-up だが、`gcloud delete --async`
  で Composer / GKE / Cloud Run しか消していない場合、IAM SA / BigQuery / Pub/Sub /
  Cloud Function / Eventarc / Cloud Run (Meilisearch) などは GCP に残置
- 全件 state rm 後に `make deploy-all` を走らせると、stage1 tf-apply で
  `Error: alreadyExists` で多数の resource create が fail
- 特に IAM SA は soft-delete 30 日 window があるため、gcloud delete → 即 terraform
  create がさらに fail する罠あり

**本 module の役割**:
1. GCP 側に存在する resources を type ごとに list
2. 名前から terraform address を逆引き (静的 mapping、`infra/terraform/modules/*/main.tf`
   と一致しているか contract test で固定)
3. state に既に entry があれば skip、無ければ `terraform import` で取り込む

idempotent: 何度叩いても余分な import は走らない。`vertex_import.py` の VVS 永続化
import と同じ pattern で、deploy_all.py が tf-apply 直前に呼ぶ。

**制限**:
- IAM bindings (`google_project_iam_member` etc.) は recover しない (依存 SA を import
  してから tf-apply で create_or_read される)
- GCS buckets は force_destroy 設計が module 側で固定されているため復元しない
- 教材用 dev project (`mlops-dev-a`) 専用。別 project への流用は mapping 拡張要
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Terraform address ↔ GCP resource mapping
# `infra/terraform/modules/*/main.tf` の resource declaration と一致させる。
# 不一致は `tests/integration/workflow/test_state_recovery_contract.py` で検出。
# ---------------------------------------------------------------------------

# IAM service accounts: account_id 'sa-X' → terraform address `module.iam.google_service_account.X`
# (X は dash-to-underscore 変換。例: sa-job-train → job_train)
IAM_SA_NAMES = (
    "api",
    "job_train",
    "job_embed",
    "dataform",
    "scheduler",
    "pipeline",
    "endpoint_encoder",
    "endpoint_reranker",
    "pipeline_trigger",
    "external_secrets",
    "github_deployer",
    "composer",
)

# BQ datasets (module.data)
BQ_DATASETS = ("mlops", "feature_mart", "predictions")

# BQ tables: (dataset, table_name, terraform_resource_name)
# table_name は GCP の table ID、terraform_resource_name は main.tf の resource label
BQ_TABLES = (
    ("mlops", "training_runs", "training_runs"),
    ("mlops", "search_logs", "search_logs"),
    ("mlops", "ranking_log", "ranking_log"),
    ("mlops", "feedback_events", "feedback_events"),
    ("mlops", "validation_results", "validation_results"),
    ("mlops", "model_monitoring_alerts", "model_monitoring_alerts"),
    ("mlops", "ranking_log_hourly_ctr", "ranking_log_hourly_ctr"),
    ("feature_mart", "property_features_daily", "property_features_daily"),
    ("feature_mart", "property_features_online_latest", "property_features_online_latest"),
    ("feature_mart", "property_embeddings", "property_embeddings"),
)

# Pub/Sub topics: (gcp_topic_name, module_name, terraform_resource_name)
PUBSUB_TOPICS = (
    ("ranking-log", "messaging", "ranking_log"),
    ("search-feedback", "messaging", "search_feedback"),
    ("retrain-trigger", "messaging", "retrain_trigger"),
    ("model-monitoring-alerts", "vertex", "model_monitoring_alerts"),
)

# Pub/Sub subscriptions: (gcp_sub_name, module_name, terraform_resource_name)
PUBSUB_SUBSCRIPTIONS = (
    ("ranking-log-to-bq", "messaging", "ranking_log_to_bq"),
    ("search-feedback-to-bq", "messaging", "search_feedback_to_bq"),
    ("monitoring-alerts-to-bq", "vertex", "monitoring_alerts_to_bq"),
)

# Cloud Function (Gen 2): (gcp_function_name, module_name, terraform_resource_name)
CLOUD_FUNCTIONS = (("pipeline-trigger", "vertex", "pipeline_trigger"),)

# Eventarc triggers: (gcp_trigger_name, module_name, terraform_resource_name)
EVENTARC_TRIGGERS = (
    ("retrain-to-pipeline", "vertex", "retrain_to_pipeline"),
    ("monitoring-to-pipeline", "vertex", "monitoring_to_pipeline"),
)

# Cloud Run services: (gcp_service_name, module_name, terraform_resource_name)
CLOUD_RUN_SERVICES = (("meili-search", "meilisearch", "meili_search"),)

# Artifact Registry repositories: (gcp_repo_id, module_name, terraform_resource_name)
# `var.artifact_repo_id` default = "mlops" (`environments/dev/variables.tf`)。
ARTIFACT_REGISTRY_REPOS = (("mlops", "data", "mlops"),)

# Secret Manager secrets: (gcp_secret_id, module_name, terraform_resource_name)
SECRET_MANAGER_SECRETS = (
    ("meili-master-key", "data", "meili_master_key"),
    ("search-api-iap-oauth-client-secret", "data", "search_api_iap_oauth_client_secret"),
)

# Dataform repositories: (gcp_repo_name, module_name, terraform_resource_name)
# `var.dataform_repository_id` default = "hybrid-search-cloud"。
DATAFORM_REPOS = (("hybrid-search-cloud", "data", "main"),)

# GCS buckets: (gcp_bucket_name, module_name, terraform_resource_name)
# 名前は `environments/dev/variables.tf` の var default (= mlops-dev-a プロジェクト前提)。
# tfstate bucket 自身 (`mlops-dev-a-tfstate`) は terraform 管理外のため対象外。
GCS_BUCKETS = (
    ("mlops-dev-a-models", "data", "models"),
    ("mlops-dev-a-artifacts", "data", "artifacts"),
    ("mlops-dev-a-pipeline-root", "data", "pipeline_root"),
    ("mlops-dev-a-meili-data", "meilisearch", "meili_data"),
)

# Vertex AI Feature Store: (gcp_id, module_name, terraform_resource_name)
# `count = enable_feature_group ? 1 : 0` のため address suffix は `[0]`。
# defaults: feature_group_id=property_features / feature_online_store_id=mlops_dev_feature_store
# / feature_view_id=property_features
FEATURE_GROUPS = (("property_features", "vertex", "property_features"),)
FEATURE_ONLINE_STORES = (("mlops_dev_feature_store", "vertex", "property_features"),)
FEATURE_VIEWS = (("mlops_dev_feature_store", "property_features", "vertex", "property_features"),)

# Vertex AI Feature Group Features: (feature_group_id, feature_id, module_name, terraform_resource_name)
# `for_each` resource なので address suffix は `["<feature_id>"]`。
# 名前は `infra/terraform/modules/vertex/main.tf::local.feature_group_property_features` の name と一致させる。
FEATURE_GROUP_FEATURES = tuple(
    ("property_features", feat, "vertex", "property_features")
    for feat in ("rent", "walk_min", "age_years", "area_m2", "ctr", "fav_rate", "inquiry_rate")
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _state_has(infra_dir: Path, addr: str) -> bool:
    """terraform state list <addr> が hit するか。"""
    proc = subprocess.run(
        ["terraform", f"-chdir={infra_dir}", "state", "list", addr],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and addr in (proc.stdout or "")


def _terraform_import(
    infra_dir: Path, addr: str, gcp_id: str, *, terraform_var_args: list[str]
) -> bool:
    print(f"==> terraform import {addr} ← {gcp_id}")
    proc = subprocess.run(
        [
            "terraform",
            f"-chdir={infra_dir}",
            "import",
            *terraform_var_args,
            addr,
            gcp_id,
        ],
        check=False,
    )
    return proc.returncode == 0


def _gcloud_json(args: list[str]) -> list[dict]:
    """gcloud `--format=json` の結果を list[dict] に。失敗時は []。"""
    proc = subprocess.run(args, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    try:
        payload = json.loads(proc.stdout) if (proc.stdout or "").strip() else []
        return payload if isinstance(payload, list) else []
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# IAM SA recovery
# ---------------------------------------------------------------------------


def _recover_iam_sas(infra_dir: Path, project_id: str, var_args: list[str]) -> int:
    imported = 0
    existing = _gcloud_json(
        ["gcloud", "iam", "service-accounts", "list", f"--project={project_id}", "--format=json"]
    )
    existing_emails = {sa.get("email", "") for sa in existing}
    for sa_name in IAM_SA_NAMES:
        addr = f"module.iam.google_service_account.{sa_name}"
        # account_id は dash 区切り (terraform `sa-{tf_name.replace("_","-")}`)
        # ただし terraform `account_id` field は main.tf 内で個別指定。確実な mapping は
        # email = sa-{tf_name.replace("_","-")}@<project>.iam.gserviceaccount.com
        gcp_account_id = "sa-" + sa_name.replace("_", "-")
        email = f"{gcp_account_id}@{project_id}.iam.gserviceaccount.com"
        if email not in existing_emails:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_resource_name = f"projects/{project_id}/serviceAccounts/{email}"
        if _terraform_import(infra_dir, addr, gcp_resource_name, terraform_var_args=var_args):
            imported += 1
    return imported


# ---------------------------------------------------------------------------
# BigQuery dataset / table recovery
# ---------------------------------------------------------------------------


def _bq_exists(project_id: str, gcp_id: str) -> bool:
    """bq show GCP_ID returns 0 if exists."""
    proc = subprocess.run(
        ["bq", "show", "--project_id", project_id, "--format=none", gcp_id],
        check=False,
        capture_output=True,
    )
    return proc.returncode == 0


def _recover_bq(infra_dir: Path, project_id: str, var_args: list[str]) -> int:
    imported = 0
    for ds in BQ_DATASETS:
        addr = f"module.data.google_bigquery_dataset.{ds}"
        gcp_id = f"projects/{project_id}/datasets/{ds}"
        if not _bq_exists(project_id, f"{project_id}:{ds}"):
            continue
        if _state_has(infra_dir, addr):
            continue
        if _terraform_import(infra_dir, addr, gcp_id, terraform_var_args=var_args):
            imported += 1
    for ds, tbl, tf_name in BQ_TABLES:
        addr = f"module.data.google_bigquery_table.{tf_name}"
        gcp_id = f"projects/{project_id}/datasets/{ds}/tables/{tbl}"
        if not _bq_exists(project_id, f"{project_id}:{ds}.{tbl}"):
            continue
        if _state_has(infra_dir, addr):
            continue
        if _terraform_import(infra_dir, addr, gcp_id, terraform_var_args=var_args):
            imported += 1
    return imported


# ---------------------------------------------------------------------------
# Pub/Sub topic / subscription recovery
# ---------------------------------------------------------------------------


def _recover_pubsub(infra_dir: Path, project_id: str, var_args: list[str]) -> int:
    imported = 0
    existing_topics = {
        t.get("name", "").rsplit("/", 1)[-1]
        for t in _gcloud_json(
            ["gcloud", "pubsub", "topics", "list", f"--project={project_id}", "--format=json"]
        )
    }
    for gcp_name, module, tf_name in PUBSUB_TOPICS:
        addr = f"module.{module}.google_pubsub_topic.{tf_name}"
        if gcp_name not in existing_topics:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_id = f"projects/{project_id}/topics/{gcp_name}"
        if _terraform_import(infra_dir, addr, gcp_id, terraform_var_args=var_args):
            imported += 1
    existing_subs = {
        s.get("name", "").rsplit("/", 1)[-1]
        for s in _gcloud_json(
            [
                "gcloud",
                "pubsub",
                "subscriptions",
                "list",
                f"--project={project_id}",
                "--format=json",
            ]
        )
    }
    for gcp_name, module, tf_name in PUBSUB_SUBSCRIPTIONS:
        addr = f"module.{module}.google_pubsub_subscription.{tf_name}"
        if gcp_name not in existing_subs:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_id = f"projects/{project_id}/subscriptions/{gcp_name}"
        if _terraform_import(infra_dir, addr, gcp_id, terraform_var_args=var_args):
            imported += 1
    return imported


# ---------------------------------------------------------------------------
# Cloud Function / Eventarc / Cloud Run recovery
# ---------------------------------------------------------------------------


def _recover_cloudfunctions(
    infra_dir: Path, project_id: str, region: str, var_args: list[str]
) -> int:
    imported = 0
    existing = {
        f.get("name", "").rsplit("/", 1)[-1]
        for f in _gcloud_json(
            [
                "gcloud",
                "functions",
                "list",
                f"--project={project_id}",
                f"--regions={region}",
                "--format=json",
            ]
        )
    }
    for gcp_name, module, tf_name in CLOUD_FUNCTIONS:
        addr = f"module.{module}.google_cloudfunctions2_function.{tf_name}"
        if gcp_name not in existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_id = f"projects/{project_id}/locations/{region}/functions/{gcp_name}"
        if _terraform_import(infra_dir, addr, gcp_id, terraform_var_args=var_args):
            imported += 1
    return imported


def _recover_eventarc(infra_dir: Path, project_id: str, region: str, var_args: list[str]) -> int:
    imported = 0
    existing = {
        t.get("name", "").rsplit("/", 1)[-1]
        for t in _gcloud_json(
            [
                "gcloud",
                "eventarc",
                "triggers",
                "list",
                f"--project={project_id}",
                f"--location={region}",
                "--format=json",
            ]
        )
    }
    for gcp_name, module, tf_name in EVENTARC_TRIGGERS:
        addr = f"module.{module}.google_eventarc_trigger.{tf_name}"
        if gcp_name not in existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_id = f"projects/{project_id}/locations/{region}/triggers/{gcp_name}"
        if _terraform_import(infra_dir, addr, gcp_id, terraform_var_args=var_args):
            imported += 1
    return imported


def _recover_cloud_run(infra_dir: Path, project_id: str, region: str, var_args: list[str]) -> int:
    imported = 0
    existing = {
        s.get("metadata", {}).get("name", "")
        for s in _gcloud_json(
            [
                "gcloud",
                "run",
                "services",
                "list",
                f"--project={project_id}",
                f"--region={region}",
                "--format=json",
            ]
        )
    }
    for gcp_name, module, tf_name in CLOUD_RUN_SERVICES:
        addr = f"module.{module}.google_cloud_run_v2_service.{tf_name}"
        if gcp_name not in existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_id = f"projects/{project_id}/locations/{region}/services/{gcp_name}"
        if _terraform_import(infra_dir, addr, gcp_id, terraform_var_args=var_args):
            imported += 1
    return imported


def _recover_artifact_registry(
    infra_dir: Path, project_id: str, region: str, var_args: list[str]
) -> int:
    imported = 0
    existing = {
        r.get("name", "").rsplit("/", 1)[-1]
        for r in _gcloud_json(
            [
                "gcloud",
                "artifacts",
                "repositories",
                "list",
                f"--project={project_id}",
                f"--location={region}",
                "--format=json",
            ]
        )
    }
    for gcp_id, module, tf_name in ARTIFACT_REGISTRY_REPOS:
        addr = f"module.{module}.google_artifact_registry_repository.{tf_name}"
        if gcp_id not in existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_resource = f"projects/{project_id}/locations/{region}/repositories/{gcp_id}"
        if _terraform_import(infra_dir, addr, gcp_resource, terraform_var_args=var_args):
            imported += 1
    return imported


def _recover_secret_manager(infra_dir: Path, project_id: str, var_args: list[str]) -> int:
    imported = 0
    existing = {
        s.get("name", "").rsplit("/", 1)[-1]
        for s in _gcloud_json(
            ["gcloud", "secrets", "list", f"--project={project_id}", "--format=json"]
        )
    }
    for gcp_id, module, tf_name in SECRET_MANAGER_SECRETS:
        addr = f"module.{module}.google_secret_manager_secret.{tf_name}"
        if gcp_id not in existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_resource = f"projects/{project_id}/secrets/{gcp_id}"
        if _terraform_import(infra_dir, addr, gcp_resource, terraform_var_args=var_args):
            imported += 1
    return imported


def _recover_gcs_buckets(infra_dir: Path, project_id: str, var_args: list[str]) -> int:
    """GCS buckets — `gcloud storage buckets list` で existing を取得し import。

    bucket は `var.{name}_bucket_name` で `mlops-dev-a-{models,artifacts,pipeline-root,meili-data}`。
    tfstate bucket (`mlops-dev-a-tfstate`) は terraform 管理外のため除外。
    """
    imported = 0
    proc = subprocess.run(
        [
            "gcloud",
            "storage",
            "buckets",
            "list",
            f"--project={project_id}",
            "--format=value(name)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0
    existing = {line.strip() for line in (proc.stdout or "").splitlines() if line.strip()}
    for gcp_name, module, tf_name in GCS_BUCKETS:
        addr = f"module.{module}.google_storage_bucket.{tf_name}"
        if gcp_name not in existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        # GCS bucket import ID is the bucket name itself
        if _terraform_import(infra_dir, addr, gcp_name, terraform_var_args=var_args):
            imported += 1
    return imported


def _aiplatform_get(token: str, url: str) -> dict:
    """Vertex AI REST API GET — gcloud に直接 list subcommand が無い resource 用."""
    proc = subprocess.run(
        ["curl", "-sS", "-H", f"Authorization: Bearer {token}", url],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout) if (proc.stdout or "").strip() else {}
    except json.JSONDecodeError:
        return {}


def _recover_feature_store(
    infra_dir: Path, project_id: str, region: str, var_args: list[str]
) -> int:
    """Vertex AI Feature Group / Feature Online Store / Feature View — REST API 経由."""
    imported = 0
    proc = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0
    token = (proc.stdout or "").strip()
    base = f"https://{region}-aiplatform.googleapis.com/v1beta1/projects/{project_id}/locations/{region}"

    # Feature Groups
    fg_payload = _aiplatform_get(token, f"{base}/featureGroups")
    fg_existing = {
        r.get("name", "").rsplit("/", 1)[-1] for r in (fg_payload.get("featureGroups") or [])
    }
    for gcp_id, module, tf_name in FEATURE_GROUPS:
        addr = f"module.{module}.google_vertex_ai_feature_group.{tf_name}[0]"
        if gcp_id not in fg_existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_resource = f"projects/{project_id}/locations/{region}/featureGroups/{gcp_id}"
        if _terraform_import(infra_dir, addr, gcp_resource, terraform_var_args=var_args):
            imported += 1

    # Feature Online Stores
    fos_payload = _aiplatform_get(token, f"{base}/featureOnlineStores")
    fos_existing = {
        r.get("name", "").rsplit("/", 1)[-1] for r in (fos_payload.get("featureOnlineStores") or [])
    }
    for gcp_id, module, tf_name in FEATURE_ONLINE_STORES:
        addr = f"module.{module}.google_vertex_ai_feature_online_store.{tf_name}[0]"
        if gcp_id not in fos_existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_resource = f"projects/{project_id}/locations/{region}/featureOnlineStores/{gcp_id}"
        if _terraform_import(infra_dir, addr, gcp_resource, terraform_var_args=var_args):
            imported += 1

    # Feature Group Features (under each Feature Group)
    for fg_id, feat_id, module, tf_name in FEATURE_GROUP_FEATURES:
        if fg_id not in fg_existing:
            continue
        addr = f'module.{module}.google_vertex_ai_feature_group_feature.{tf_name}["{feat_id}"]'
        feat_payload = _aiplatform_get(token, f"{base}/featureGroups/{fg_id}/features")
        feat_existing = {
            r.get("name", "").rsplit("/", 1)[-1] for r in (feat_payload.get("features") or [])
        }
        if feat_id not in feat_existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_resource = (
            f"projects/{project_id}/locations/{region}/featureGroups/{fg_id}/features/{feat_id}"
        )
        if _terraform_import(infra_dir, addr, gcp_resource, terraform_var_args=var_args):
            imported += 1

    # Feature Views (under each Feature Online Store)
    for fos_id, fv_id, module, tf_name in FEATURE_VIEWS:
        if fos_id not in fos_existing:
            continue
        addr = f"module.{module}.google_vertex_ai_feature_online_store_featureview.{tf_name}[0]"
        fv_payload = _aiplatform_get(token, f"{base}/featureOnlineStores/{fos_id}/featureViews")
        fv_existing = {
            r.get("name", "").rsplit("/", 1)[-1] for r in (fv_payload.get("featureViews") or [])
        }
        if fv_id not in fv_existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_resource = (
            f"projects/{project_id}/locations/{region}/featureOnlineStores/"
            f"{fos_id}/featureViews/{fv_id}"
        )
        if _terraform_import(infra_dir, addr, gcp_resource, terraform_var_args=var_args):
            imported += 1
    return imported


def _recover_dataform(infra_dir: Path, project_id: str, region: str, var_args: list[str]) -> int:
    """Dataform repositories — gcloud has no list subcommand, fall back to direct API."""
    imported = 0
    # Use REST API directly via gcloud's default access token
    proc = subprocess.run(
        [
            "gcloud",
            "auth",
            "print-access-token",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0
    token = (proc.stdout or "").strip()
    api_proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-H",
            f"Authorization: Bearer {token}",
            f"https://dataform.googleapis.com/v1beta1/projects/{project_id}/locations/{region}/repositories",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if api_proc.returncode != 0:
        return 0
    try:
        payload = json.loads(api_proc.stdout) if api_proc.stdout.strip() else {}
    except json.JSONDecodeError:
        return 0
    existing = {r.get("name", "").rsplit("/", 1)[-1] for r in (payload.get("repositories") or [])}
    for gcp_id, module, tf_name in DATAFORM_REPOS:
        addr = f"module.{module}.google_dataform_repository.{tf_name}"
        if gcp_id not in existing:
            continue
        if _state_has(infra_dir, addr):
            continue
        gcp_resource = f"projects/{project_id}/locations/{region}/repositories/{gcp_id}"
        if _terraform_import(infra_dir, addr, gcp_resource, terraform_var_args=var_args):
            imported += 1
    return imported


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


def recover_orphan_gcp_resources(
    infra_dir: Path,
    project_id: str,
    region: str,
    *,
    terraform_var_args: list[str] | None = None,
) -> int:
    """Discover existing GCP resources and import missing ones into tfstate.

    Returns the total number of resources imported.
    """
    var_args = list(terraform_var_args or [])
    print(f"==> state recovery: project={project_id} region={region}")
    total = 0
    total += _recover_iam_sas(infra_dir, project_id, var_args)
    total += _recover_bq(infra_dir, project_id, var_args)
    total += _recover_pubsub(infra_dir, project_id, var_args)
    total += _recover_cloudfunctions(infra_dir, project_id, region, var_args)
    total += _recover_eventarc(infra_dir, project_id, region, var_args)
    total += _recover_cloud_run(infra_dir, project_id, region, var_args)
    total += _recover_artifact_registry(infra_dir, project_id, region, var_args)
    total += _recover_secret_manager(infra_dir, project_id, var_args)
    total += _recover_dataform(infra_dir, project_id, region, var_args)
    total += _recover_gcs_buckets(infra_dir, project_id, var_args)
    total += _recover_feature_store(infra_dir, project_id, region, var_args)
    if total:
        print(f"==> state recovery: {total} orphan GCP resource(s) imported into state")
    else:
        print("==> state recovery: no orphan resources found")
    return total


def main(argv: list[str] | None = None) -> int:
    """CLI: invoke recovery directly (used by `make state-recover` smoke)."""
    import os

    project_id = os.environ.get("PROJECT_ID", "mlops-dev-a")
    region = os.environ.get("VERTEX_LOCATION") or os.environ.get("REGION") or "asia-northeast1"
    infra_dir = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "environments" / "dev"
    var_args: list[str] = []
    github_repo = os.environ.get("GITHUB_REPO", "").strip()
    if github_repo:
        var_args.extend(["-var", f"github_repo={github_repo}"])
    oncall = os.environ.get("ONCALL_EMAIL", "").strip()
    if oncall:
        var_args.extend(["-var", f"oncall_email={oncall}"])
    recover_orphan_gcp_resources(infra_dir, project_id, region, terraform_var_args=var_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
