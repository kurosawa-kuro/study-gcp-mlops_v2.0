# ----- Runtime Service Accounts (5 SA 分離) -----

resource "google_service_account" "api" {
  account_id   = "sa-api"
  display_name = "Cloud Run Service (FastAPI) runtime SA"
}

resource "google_service_account" "job_train" {
  account_id   = "sa-job-train"
  display_name = "Cloud Run Jobs (LightGBM LambdaRank training) runtime SA"
}

resource "google_service_account" "job_embed" {
  account_id   = "sa-job-embed"
  display_name = "Cloud Run Jobs (multilingual-e5 embedding batch) runtime SA"
}

resource "google_service_account" "dataform" {
  account_id   = "sa-dataform"
  display_name = "Dataform service SA (feature mart writer)"
}

resource "google_service_account" "scheduler" {
  account_id   = "sa-scheduler"
  display_name = "Cloud Scheduler SA (invoke API / publish retrain trigger)"
}

resource "google_service_account" "pipeline" {
  account_id   = "sa-pipeline"
  display_name = "Vertex AI Pipelines runtime SA"
}

resource "google_service_account" "endpoint_encoder" {
  account_id   = "sa-endpoint-encoder"
  display_name = "Vertex AI encoder endpoint runtime SA"
}

resource "google_service_account" "endpoint_reranker" {
  account_id   = "sa-endpoint-reranker"
  display_name = "Vertex AI reranker endpoint runtime SA"
}

resource "google_service_account" "pipeline_trigger" {
  account_id   = "sa-pipeline-trigger"
  display_name = "Vertex pipeline trigger runtime SA"
}

resource "google_service_account" "external_secrets" {
  account_id   = "sa-external-secrets"
  display_name = "External Secrets Operator controller SA"
}

# ----- Workload Identity Federation for GitHub Actions -----

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == \"${var.github_repo}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "github_deployer" {
  account_id   = "sa-github-deployer"
  display_name = "GitHub Actions deployer (via WIF)"
}

resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# ---------------------------------------------------------------------------
# Admin user → sa-api TokenCreator (local-ops impersonation).
#
# Meilisearch の初期 document sync は sa-api identity (audience = meili-search
# Cloud Run URL) での OIDC token が必須。開発者 user account が
# `gcloud auth print-identity-token --impersonate-service-account=sa-api
# --audiences=...` を叩くには TokenCreator 権限が要る。Phase 5 の実運用で
# ここが漏れて 2 時間ハマった教訓を Terraform 化して自動化する。
#
# admin_user_emails は `env/config/setting.yaml` 経由で渡す想定 (empty list
# なら binding 無し)。
# ---------------------------------------------------------------------------
resource "google_service_account_iam_member" "api_token_creator_for_admins" {
  for_each           = toset(var.admin_user_emails)
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${each.value}"
}

# Deployer needs enough power to run terraform apply + gcloud deploys.
# Keep it a single role for this PoC; tighten later.
resource "google_project_iam_member" "github_deployer_editor" {
  project = var.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "github_deployer_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# ----- Project-level IAM for runtime SAs -----

resource "google_project_iam_member" "api_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# GKE Autopilot's Managed Prometheus collector runs in the gke-gmp-system
# namespace using the node's default compute engine SA. Phase 7's IAM
# lockdown stripped the project's default `roles/monitoring.metricWriter`
# binding, which causes GMP to silently drop all `prometheus.googleapis.com/*`
# metrics — the upstream cause of `module.slo` apply failing with
# "0 series found" on http_requests_total / http_request_duration_seconds.
# Re-grant the writer role to the compute default SA so /metrics scraped
# from search-api / property-* surface in Cloud Monitoring.
resource "google_project_iam_member" "gmp_compute_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_iam_member" "api_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "train_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.job_train.email}"
}

resource "google_project_iam_member" "train_bq_read_session" {
  project = var.project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.job_train.email}"
}

resource "google_project_iam_member" "embed_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.job_embed.email}"
}

resource "google_project_iam_member" "embed_bq_read_session" {
  project = var.project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.job_embed.email}"
}

resource "google_project_iam_member" "dataform_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dataform.email}"
}

resource "google_project_iam_member" "pipeline_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_bq_read_session" {
  project = var.project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_trigger_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.pipeline_trigger.email}"
}

resource "google_project_iam_member" "pipeline_trigger_eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.pipeline_trigger.email}"
}

resource "google_project_iam_member" "pipeline_trigger_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.pipeline_trigger.email}"
}

resource "google_project_iam_member" "pipeline_trigger_logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.pipeline_trigger.email}"
}

resource "google_service_account_iam_member" "pipeline_trigger_can_use_pipeline_sa" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.pipeline_trigger.email}"
}

# Composer Pod (Workload Identity = sa-composer) runs `submit_train_pipeline`,
# which calls `PipelineJob.submit(service_account=sa-pipeline@...)`. The caller
# must have iam.serviceAccountUser on the pipeline runtime SA (same pattern as
# pipeline_trigger_can_use_pipeline_sa).
resource "google_service_account_iam_member" "composer_can_use_pipeline_sa" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.composer.email}"
}

resource "google_project_iam_member" "endpoint_encoder_logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.endpoint_encoder.email}"
}

resource "google_project_iam_member" "endpoint_reranker_logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.endpoint_reranker.email}"
}

# =========================================================================
# Phase 7 Wave 2 W2-3: KServe pod (reranker) → Feature Online Store の
# Feature View 経由 opt-in 参照経路で必要な権限。
#
# search-api SA (`api`) は既に roles/aiplatform.user 付与済 (line 148-152)
# なので、Vertex Vector Search find_neighbors / Feature Online Store
# fetchFeatureValues は素通りする。本ブロックは KServe encoder / reranker
# SA に対する追加 binding。
#
# - encoder: ME5 で encode するだけなので、Vertex API 呼び出し不要。
#   roles/aiplatform.user は付与しない (最小権限)。
# - reranker: Phase 7 固有経路で `FEATURE_FETCHER_BACKEND=online_store`
#   のときに Feature View 経由で fetch する想定。default off (= Wave 2 W2-8 まで
#   観測されない) だが、TF レベルでは provision 時に bind 済の方が
#   一括 PDCA で扱いやすい。
# =========================================================================

resource "google_project_iam_member" "endpoint_reranker_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.endpoint_reranker.email}"
}

# =========================================================================
# Phase 7 W2-4 (Composer canonical): Cloud Composer environment runtime SA.
#
# Composer Gen 3 環境本体が Airflow scheduler / web_server / worker pod を
# 動かすために使う SA。Phase 7 docs/architecture/01_仕様と設計.md §3 で
# Composer は **上位 orchestrator** として位置付けられ、3 本 DAG
# (`daily_feature_refresh` / `retrain_orchestration` / `monitoring_validation`)
# が Vertex Pipelines submit / BigQuery monitoring query / Feature View sync
# を invoke する。本 SA はそれらの dispatch 権限を持つ最小セット:
#
# - composer.worker: Composer 環境本体の管理 (env / config / DAG bucket)
# - aiplatform.user: Vertex Pipelines submit + Feature View read +
#   Vector Search find_neighbors / upsert_datapoints
# - bigquery.jobUser + bigquery.dataViewer: monitoring SQL 実行 + 結果 read
# - run.invoker: smoke で `/jobs/check-retrain` (search-api Gateway) を
#   POST する用 (Composer DAG の `check_retrain` task が呼ぶ)
# =========================================================================

resource "google_service_account" "composer" {
  account_id   = "sa-composer"
  display_name = "Cloud Composer environment runtime SA (Phase 7 canonical orchestrator)"
}

resource "google_project_iam_member" "composer_worker" {
  project = var.project_id
  role    = "roles/composer.worker"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

resource "google_project_iam_member" "composer_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

resource "google_project_iam_member" "composer_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

resource "google_project_iam_member" "composer_bq_data_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

resource "google_project_iam_member" "composer_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

# V5 fix (2026-05-03、§4.1): 過去 session の Claude が DAG を `BashOperator: uv
# run python -m scripts.X` で書いたが Composer worker は uv 不在 / repo source
# 不在で task SUCCEEDED 未達 (canonical 違反)。新版は KubernetesPodOperator で
# `composer-runner` image を Composer 自身の GKE 上に Pod として起動する。
#
# - artifactregistry.reader: Composer worker が `composer-runner` image を
#   Artifact Registry から pull するため。
# - storage.objectViewer: kfp / Vertex Pipelines の中間 artifact が GCS
#   `pipeline-root` bucket に書かれるので、submit_train_pipeline / pipeline_wait
#   から read できるように。
# (composer.worker は Composer 自身の GKE 上で Pod を起動する権限を含むため
# 別途 container.developer は不要。)
resource "google_project_iam_member" "composer_artifactregistry_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

resource "google_project_iam_member" "composer_storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

# Composer 環境作成 / 削除権限を deployer SA に追加 (terraform apply で
# google_composer_environment リソースを操作するため)。
resource "google_project_iam_member" "github_deployer_composer_admin" {
  project = var.project_id
  role    = "roles/composer.admin"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}
