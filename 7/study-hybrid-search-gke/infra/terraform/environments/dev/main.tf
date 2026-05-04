# =========================================================================
# Root module (Phase 7: GKE + KServe) — orchestrates sub-modules:
#   iam          → Service Accounts / WIF / project-level role bindings
#   data         → BigQuery / GCS / Artifact Registry / Secret Manager + data IAM
#   vertex       → Vertex AI Pipelines / Feature Group / Model Registry (inherited from Phase 5)
#   gke          → GKE Autopilot cluster + Workload Identity bindings
#   kserve       → KServe + cert-manager + 3 KSA (api / encoder / reranker)
#   messaging    → Pub/Sub + BQ subscription + Cloud Scheduler (Cloud Run Service を持たない)
#   meilisearch  → Cloud Run Service (BM25 lexical retrieval、Phase 5 継承)
#   monitoring   → log-based metrics / alert policies / mean-drift Scheduled Query
#   streaming    → Phase 6 T2: Dataflow streaming job scaffold
#   slo          → Phase 6 T5: formal SLOs + burn-rate alerts
#
# Shared preconditions (API enablement) live in apis.tf and are enforced via
# `depends_on = [google_project_service.enabled]` on each module call.
#
# 2 段階 apply: 初回は `-target=module.gke -target=module.iam -target=module.data`
# で cluster / IAM / storage を作り、provider.tf で kubernetes/helm provider を
# 有効化した後に全体 apply で KServe / manifests を展開する。
# =========================================================================

module "iam" {
  source = "../../modules/iam"

  project_id        = var.project_id
  github_repo       = var.github_repo
  admin_user_emails = var.admin_user_emails

  depends_on = [google_project_service.enabled]
}

module "data" {
  source = "../../modules/data"

  project_id                        = var.project_id
  region                            = var.region
  artifact_repo_id                  = var.artifact_repo_id
  models_bucket_name                = var.models_bucket_name
  pipeline_root_bucket_name         = var.pipeline_root_bucket_name
  artifacts_bucket_name             = var.artifacts_bucket_name
  service_accounts                  = module.iam.service_accounts
  github_repo                       = var.github_repo
  dataform_repository_id            = var.dataform_repository_id
  dataform_git_token_secret_version = var.dataform_git_token_secret_version
  github_deployer_sa_email          = "sa-github-deployer@${var.project_id}.iam.gserviceaccount.com"
  enable_deletion_protection        = var.enable_deletion_protection

  depends_on = [google_project_service.enabled]
}

module "vector_search" {
  source = "../../modules/vector_search"

  project_id           = var.project_id
  region               = var.region
  enable_vector_search = var.enable_vector_search

  depends_on = [google_project_service.enabled]
}

# Phase 7 W2-4: Cloud Composer (Managed Airflow Gen 3) — canonical
# orchestrator. 3 DAG (`daily_feature_refresh` / `retrain_orchestration`
# / `monitoring_validation`) を本線 schedule として走らせる。docs §3 上下
# 関係 (Composer = 上位 / Vertex Pipelines = 下位) の上位側実体。
module "composer" {
  source = "../../modules/composer"

  enable_composer                   = var.enable_composer
  project_id                        = var.project_id
  region                            = var.region
  vertex_location                   = var.vertex_location
  environment_name                  = var.composer_environment_name
  composer_service_account_email    = module.iam.service_accounts.composer.email
  pipeline_root_bucket_name         = module.data.pipeline_root_bucket.name
  pipeline_template_gcs_path        = var.pipeline_template_gcs_path
  vector_search_index_resource_name = module.vector_search.index_resource_name
  feature_online_store_id           = module.vertex.feature_online_store_id
  feature_view_id                   = module.vertex.feature_view_id
  api_external_url                  = var.api_external_url
  slo_availability_goal             = var.slo_availability_goal
  composer_runner_image             = var.composer_runner_image

  depends_on = [
    google_project_service.enabled,
    module.iam,
    module.data,
    module.vector_search,
    module.vertex,
  ]
}

module "vertex" {
  source = "../../modules/vertex"

  project_id                       = var.project_id
  region                           = var.region
  vertex_location                  = var.vertex_location
  service_accounts                 = module.iam.service_accounts
  mlops_dataset_id                 = module.data.mlops_dataset.dataset_id
  feature_mart_dataset_id          = module.data.feature_mart_dataset.dataset_id
  pipeline_root_bucket_name        = module.data.pipeline_root_bucket.name
  models_bucket_name               = module.data.models_bucket.name
  model_monitoring_alerts_table_id = module.data.model_monitoring_alerts_table.table_id
  encoder_endpoint_id              = var.vertex_encoder_endpoint_id
  reranker_endpoint_id             = var.vertex_reranker_endpoint_id
  encoder_endpoint_display_name    = "property-encoder-endpoint"
  reranker_endpoint_display_name   = "property-reranker-endpoint"
  enable_vertex_endpoint_shell     = var.enable_vertex_endpoint_shell
  retrain_trigger_topic_id         = module.messaging.retrain_trigger_topic.id
  retrain_trigger_topic_name       = module.messaging.retrain_trigger_topic.name
  enable_feature_online_store      = var.enable_feature_online_store

  depends_on = [
    google_project_service.enabled,
    module.data,
    module.iam,
    module.messaging,
  ]
}

module "gke" {
  source = "../../modules/gke"

  project_id          = var.project_id
  region              = var.region
  cluster_name        = var.gke_cluster_name
  deletion_protection = var.enable_deletion_protection
  service_accounts    = module.iam.service_accounts

  depends_on = [
    google_project_service.enabled,
    module.iam,
  ]
}

module "kserve" {
  source = "../../modules/kserve"

  ksa_names        = module.gke.ksa_names
  service_accounts = module.iam.service_accounts

  depends_on = [
    module.gke,
  ]
}

module "messaging" {
  source = "../../modules/messaging"

  project_id               = var.project_id
  region                   = var.region
  mlops_dataset_id         = module.data.mlops_dataset.dataset_id
  ranking_log_table_id     = module.data.ranking_log_table.table_id
  feedback_events_table_id = module.data.feedback_events_table.table_id
  service_accounts         = module.iam.service_accounts
  api_external_url         = var.api_external_url

  depends_on = [
    google_project_service.enabled,
    module.data,
  ]
}

module "meilisearch" {
  source = "../../modules/meilisearch"

  project_id                 = var.project_id
  region                     = var.region
  service_accounts           = module.iam.service_accounts
  meili_data_bucket_name     = var.meili_data_bucket_name
  meili_master_key_secret_id = module.data.secrets.meili_master_key.secret_id

  depends_on = [google_project_service.enabled, module.data]
}

module "monitoring" {
  source = "../../modules/monitoring"

  project_id                  = var.project_id
  region                      = var.region
  mlops_dataset_id            = module.data.mlops_dataset.dataset_id
  ranker_skew_sql_path        = "${path.root}/../../../../infra/sql/monitoring/validate_feature_skew.sql"
  model_output_drift_sql_path = "${path.root}/../../../../infra/sql/monitoring/validate_model_output_drift.sql"
  oncall_email                = var.oncall_email
  service_accounts            = module.iam.service_accounts

  depends_on = [
    google_project_service.enabled,
    module.data,
  ]
}

# Phase 6 T2 — Dataflow streaming job scaffold (ranking-log hourly CTR).
# The Flex Template image + spec JSON are built out of band; module
# creates sa-dataflow + IAM. Flip enable_streaming_job=true after the
# template is in GCS to register the streaming job itself.
module "streaming" {
  count  = var.enable_streaming ? 1 : 0
  source = "../../modules/streaming"

  project_id             = var.project_id
  region                 = var.region
  ranking_log_topic_id   = module.messaging.ranking_log_topic.id
  output_table_fqn       = "${var.project_id}:${module.data.mlops_dataset.dataset_id}.${module.data.ranking_log_hourly_ctr_table.table_id}"
  flex_template_gcs_path = var.streaming_flex_template_gcs_path
  temp_location          = "gs://${module.data.artifacts_bucket.name}/dataflow/tmp"
  staging_location       = "gs://${module.data.artifacts_bucket.name}/dataflow/staging"
  create_job             = var.enable_streaming_job

  depends_on = [
    google_project_service.enabled,
    module.data,
    module.messaging,
  ]
}

# Phase 6 T5 — formal SLOs (availability + latency) + burn-rate alerts on
# search-api GKE service. Reuses the notification channel created by
# module.monitoring so operators do not receive duplicate emails.
module "slo" {
  source = "../../modules/slo"

  project_id   = var.project_id
  region       = var.region
  service_name = "search-api"

  # Phase 7: attach SLOs to the GKE Deployment/Service, not Cloud Run. The SLI
  # filters switch to prometheus.googleapis.com/http_requests_total (exported
  # by PodMonitoring → GMP) and the telemetry anchor points at the k8s Service
  # inside the GKE Autopilot cluster.
  service_type         = "k8s_service"
  k8s_namespace        = "search"
  gke_cluster_name     = var.gke_cluster_name
  gke_cluster_location = var.region

  notification_channel_ids = [module.monitoring.notification_channel_id]

  availability_goal    = var.slo_availability_goal
  latency_threshold_ms = var.slo_latency_threshold_ms
  latency_goal         = var.slo_latency_goal
  rolling_period_days  = var.slo_rolling_period_days

  depends_on = [
    google_project_service.enabled,
    module.monitoring,
    module.gke,
  ]
}
