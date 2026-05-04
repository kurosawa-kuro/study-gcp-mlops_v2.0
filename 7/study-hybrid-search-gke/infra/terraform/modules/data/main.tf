# =========================================================================
# BigQuery — datasets + tables (schemas are load-bearing for feature parity)
# =========================================================================

resource "google_bigquery_dataset" "mlops" {
  dataset_id  = "mlops"
  location    = var.region
  description = "Lineage, prediction logs, and skew validation results"
}

resource "google_bigquery_dataset" "feature_mart" {
  dataset_id  = "feature_mart"
  location    = var.region
  description = "Dataform-managed feature mart (training/serving shared)"
}

resource "google_bigquery_dataset" "predictions" {
  dataset_id  = "predictions"
  location    = var.region
  description = "Raw prediction sink from Pub/Sub BigQuery Subscription"
}

resource "google_bigquery_table" "training_runs" {
  dataset_id          = google_bigquery_dataset.mlops.dataset_id
  table_id            = "training_runs"
  deletion_protection = var.enable_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "started_at"
  }
  clustering = ["run_id"]

  schema = jsonencode([
    { name = "run_id", type = "STRING", mode = "REQUIRED" },
    { name = "started_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "finished_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "model_path", type = "STRING", mode = "REQUIRED", description = "gs:// URI to model.txt" },
    { name = "git_sha", type = "STRING", mode = "NULLABLE" },
    { name = "dataset_version", type = "STRING", mode = "NULLABLE" },
    {
      # Ranker metrics (Phase 10c final state).
      # BigQuery does not support dropping RECORD sub-fields in-place; the legacy
      # regression fields (rmse / mae / r2 / best_iteration) that previously
      # lived here were consumed by no post-Phase-10b writer, so they are simply
      # omitted from the schema going forward. Operators recreating the table
      # via `bq rm -f` + apply land on the clean shape below.
      name = "metrics", type = "RECORD", mode = "NULLABLE",
      fields = [
        { name = "best_iteration", type = "INT64", mode = "NULLABLE" },
        { name = "ndcg_at_10", type = "FLOAT64", mode = "NULLABLE" },
        { name = "map", type = "FLOAT64", mode = "NULLABLE" },
        { name = "recall_at_20", type = "FLOAT64", mode = "NULLABLE" },
      ]
    },
    {
      name = "hyperparams", type = "RECORD", mode = "NULLABLE",
      fields = [
        { name = "num_leaves", type = "INT64", mode = "NULLABLE" },
        { name = "learning_rate", type = "FLOAT64", mode = "NULLABLE" },
        { name = "feature_fraction", type = "FLOAT64", mode = "NULLABLE" },
        { name = "bagging_fraction", type = "FLOAT64", mode = "NULLABLE" },
        { name = "num_iterations", type = "INT64", mode = "NULLABLE" },
        { name = "early_stopping_rounds", type = "INT64", mode = "NULLABLE" },
        { name = "min_data_in_leaf", type = "INT64", mode = "NULLABLE" },
        { name = "lambdarank_truncation_level", type = "INT64", mode = "NULLABLE" },
      ]
    },
  ])
}

# =========================================================================
# Phase 10c removed: google_bigquery_table.predictions_log
#
# The legacy California single-value prediction log is fully retired. Operators
# performing the in-place migration on an existing project must run:
#
#   bq update --project_id=mlops-dev-a \
#     --no_deletion_protection mlops.predictions_log
#   bq rm -f --project_id=mlops-dev-a -t mlops.predictions_log
#
# *before* the next `terraform apply`, because the resource previously carried
# ``deletion_protection = true``. See ``docs/runbook/05_運用.md §3.9`` for the full
# two-phase apply checklist.
# =========================================================================

# =========================================================================
# Real-estate hybrid search tables (Phase 1+, authoritative after Phase 10c).
#
#   feature_mart.property_features_daily — Dataform-managed daily aggregates
#                                          (ctr / fav_rate / inquiry_rate).
#   feature_mart.property_embeddings     — 768d multilingual-e5-base vectors
#                                          written by the embedding-job.
#   mlops.search_logs                    — one row per /search invocation.
#   mlops.ranking_log                    — one row per (request_id, property_id)
#                                          candidate with features + ranks.
#   mlops.feedback_events                — click / favorite / inquiry events.
#
# Feature parity invariant for ranker:
#   definitions/features/property_features_daily.sqlx
#   ml/data/feature_engineering/ranker_features.py::build_ranker_features
#   ml/data/feature_engineering/schema.py::FEATURE_COLS_RANKER
#   THIS file (ranking_log.features RECORD)
#   infra/sql/monitoring/validate_feature_skew.sql
# =========================================================================

resource "google_bigquery_table" "property_features_daily" {
  dataset_id          = google_bigquery_dataset.feature_mart.dataset_id
  table_id            = "property_features_daily"
  deletion_protection = var.enable_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "event_date"
  }
  clustering = ["property_id"]

  schema = jsonencode([
    { name = "event_date", type = "DATE", mode = "REQUIRED" },
    { name = "feature_timestamp", type = "TIMESTAMP", mode = "NULLABLE", description = "Feature-time column required by Vertex AI Feature Group BigQuery source" },
    { name = "property_id", type = "STRING", mode = "REQUIRED" },
    { name = "rent", type = "INT64", mode = "NULLABLE" },
    { name = "walk_min", type = "INT64", mode = "NULLABLE" },
    { name = "age_years", type = "INT64", mode = "NULLABLE" },
    { name = "area_m2", type = "FLOAT64", mode = "NULLABLE" },
    { name = "ctr", type = "FLOAT64", mode = "NULLABLE" },
    { name = "fav_rate", type = "FLOAT64", mode = "NULLABLE" },
    { name = "inquiry_rate", type = "FLOAT64", mode = "NULLABLE" },
    { name = "popularity_score", type = "FLOAT64", mode = "NULLABLE", description = "Fallback ranking score when LightGBM booster is unavailable" },
  ])
}

# Online-serving canonical source for Vertex Feature View.
# Keep only one row per property_id (today's slice) and exclude control
# columns such as event_date so Feature View direct BigQuery source accepts
# the schema.
resource "google_bigquery_table" "property_features_online_latest" {
  dataset_id          = google_bigquery_dataset.feature_mart.dataset_id
  table_id            = "property_features_online_latest"
  deletion_protection = var.enable_deletion_protection
  depends_on          = [google_bigquery_table.property_features_daily]

  view {
    use_legacy_sql = false
    query = <<-SQL
      SELECT
        property_id,
        rent,
        walk_min,
        age_years,
        area_m2,
        ctr,
        fav_rate,
        inquiry_rate
      FROM `${var.project_id}.${google_bigquery_dataset.feature_mart.dataset_id}.property_features_daily`
      WHERE event_date = CURRENT_DATE("Asia/Tokyo")
    SQL
  }
}

resource "google_bigquery_table" "property_embeddings" {
  dataset_id          = google_bigquery_dataset.feature_mart.dataset_id
  table_id            = "property_embeddings"
  deletion_protection = var.enable_deletion_protection

  clustering = ["property_id"]

  schema = jsonencode([
    { name = "property_id", type = "STRING", mode = "REQUIRED" },
    { name = "embedding", type = "FLOAT64", mode = "REPEATED", description = "768d normalized vector from intfloat/multilingual-e5-base" },
    { name = "text_hash", type = "STRING", mode = "REQUIRED", description = "sha256(title || description) — skip re-encoding if unchanged" },
    { name = "model_name", type = "STRING", mode = "REQUIRED" },
    { name = "generated_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "search_logs" {
  dataset_id          = google_bigquery_dataset.mlops.dataset_id
  table_id            = "search_logs"
  deletion_protection = var.enable_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "ts"
  }
  clustering = ["request_id"]

  schema = jsonencode([
    { name = "request_id", type = "STRING", mode = "REQUIRED" },
    { name = "ts", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "query", type = "STRING", mode = "REQUIRED" },
    {
      name = "filters", type = "RECORD", mode = "NULLABLE",
      fields = [
        { name = "max_rent", type = "INT64", mode = "NULLABLE" },
        { name = "layout", type = "STRING", mode = "NULLABLE" },
        { name = "max_walk_min", type = "INT64", mode = "NULLABLE" },
        { name = "pet_ok", type = "BOOL", mode = "NULLABLE" },
        { name = "max_age", type = "INT64", mode = "NULLABLE" },
      ]
    },
    { name = "top_k", type = "INT64", mode = "REQUIRED" },
    { name = "result_property_ids", type = "STRING", mode = "REPEATED" },
    { name = "model_path", type = "STRING", mode = "NULLABLE", description = "NULL while rerank is disabled (Phase 4 minimum). Populated once booster is wired in." },
    { name = "latency_ms", type = "FLOAT64", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "ranking_log" {
  dataset_id          = google_bigquery_dataset.mlops.dataset_id
  table_id            = "ranking_log"
  deletion_protection = var.enable_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "ts"
  }
  clustering = ["request_id", "property_id"]

  schema = jsonencode([
    { name = "request_id", type = "STRING", mode = "REQUIRED" },
    { name = "ts", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "property_id", type = "STRING", mode = "REQUIRED" },
    { name = "schema_version", type = "INT64", mode = "NULLABLE", description = "Ranking log schema version. v2 introduces separated lexical/semantic ranks." },
    { name = "lexical_rank", type = "INT64", mode = "REQUIRED", description = "Initial rank from lexical retrieval (Meilisearch BM25)" },
    { name = "semantic_rank", type = "INT64", mode = "NULLABLE", description = "Initial rank from BigQuery VECTOR_SEARCH" },
    { name = "rrf_rank", type = "INT64", mode = "NULLABLE", description = "Rank after RRF fusion before LambdaRank rerank" },
    { name = "final_rank", type = "INT64", mode = "NULLABLE", description = "Post-rerank rank. Equals lexical_rank until Phase 6 wires the booster." },
    { name = "score", type = "FLOAT64", mode = "NULLABLE", description = "booster.predict() output; NULL while rerank disabled" },
    { name = "me5_score", type = "FLOAT64", mode = "NULLABLE", description = "cosine(query_vec, property_vec)" },
    {
      # Feature parity invariant — MUST match FEATURE_COLS_RANKER order-wise.
      name = "features", type = "RECORD", mode = "NULLABLE",
      fields = [
        { name = "rent", type = "FLOAT64", mode = "NULLABLE" },
        { name = "walk_min", type = "FLOAT64", mode = "NULLABLE" },
        { name = "age_years", type = "FLOAT64", mode = "NULLABLE" },
        { name = "area_m2", type = "FLOAT64", mode = "NULLABLE" },
        { name = "ctr", type = "FLOAT64", mode = "NULLABLE" },
        { name = "fav_rate", type = "FLOAT64", mode = "NULLABLE" },
        { name = "inquiry_rate", type = "FLOAT64", mode = "NULLABLE" },
        { name = "me5_score", type = "FLOAT64", mode = "NULLABLE" },
        { name = "lexical_rank", type = "FLOAT64", mode = "NULLABLE" },
        { name = "semantic_rank", type = "FLOAT64", mode = "NULLABLE" },
      ]
    },
    { name = "model_path", type = "STRING", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "feedback_events" {
  dataset_id          = google_bigquery_dataset.mlops.dataset_id
  table_id            = "feedback_events"
  deletion_protection = var.enable_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "ts"
  }
  clustering = ["request_id", "property_id"]

  schema = jsonencode([
    { name = "request_id", type = "STRING", mode = "REQUIRED" },
    { name = "property_id", type = "STRING", mode = "REQUIRED" },
    { name = "action", type = "STRING", mode = "REQUIRED", description = "click | favorite | inquiry" },
    { name = "ts", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "validation_results" {
  dataset_id          = google_bigquery_dataset.mlops.dataset_id
  table_id            = "validation_results"
  deletion_protection = var.enable_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "run_date"
  }

  schema = jsonencode([
    { name = "run_date", type = "DATE", mode = "REQUIRED" },
    { name = "metric", type = "STRING", mode = "REQUIRED" },
    { name = "feature_name", type = "STRING", mode = "NULLABLE" },
    { name = "value", type = "FLOAT64", mode = "NULLABLE" },
    { name = "threshold", type = "FLOAT64", mode = "NULLABLE" },
    { name = "status", type = "STRING", mode = "REQUIRED", description = "OK / WARN / FAIL" },
  ])
}

resource "google_bigquery_table" "model_monitoring_alerts" {
  dataset_id          = google_bigquery_dataset.mlops.dataset_id
  table_id            = "model_monitoring_alerts"
  deletion_protection = var.enable_deletion_protection
  description         = "Phase 7 drift alert sink. Legacy Vertex Model Monitoring v2 writes may still arrive if endpoint-based monitoring is re-enabled; current primary writer is the self-managed Scheduled Query that derives KServe drift signals from mlops.ranking_log."

  time_partitioning {
    type  = "DAY"
    field = "alert_time"
  }

  schema = jsonencode([
    { name = "alert_time", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "model_resource_name", type = "STRING", mode = "NULLABLE" },
    { name = "drift_metric", type = "STRING", mode = "NULLABLE" },
    { name = "feature_name", type = "STRING", mode = "NULLABLE" },
    { name = "score", type = "FLOAT64", mode = "NULLABLE" },
    { name = "threshold", type = "FLOAT64", mode = "NULLABLE" },
    { name = "payload", type = "JSON", mode = "NULLABLE" },
  ])
}

# Phase 6 T2 — Dataflow streaming sink. ranking-log events are aggregated
# in 1-hour tumbling windows into this table; runs alongside the existing
# BQ Subscription-based mlops.ranking_log raw writes.
resource "google_bigquery_table" "ranking_log_hourly_ctr" {
  dataset_id          = google_bigquery_dataset.mlops.dataset_id
  table_id            = "ranking_log_hourly_ctr"
  deletion_protection = var.enable_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "window_start"
  }

  schema = jsonencode([
    { name = "window_start", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "window_end", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "property_id", type = "STRING", mode = "REQUIRED" },
    { name = "impressions", type = "INT64", mode = "REQUIRED" },
    { name = "clicks", type = "INT64", mode = "REQUIRED" },
    { name = "ctr", type = "FLOAT64", mode = "NULLABLE", description = "SAFE_DIVIDE(clicks, impressions)" },
  ])
}

# =========================================================================
# GCS — model artifacts + general-purpose artifacts
# =========================================================================

resource "google_storage_bucket" "models" {
  name                        = var.models_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}

resource "google_storage_bucket" "artifacts" {
  name                        = var.artifacts_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = 14
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket" "pipeline_root" {
  name                        = var.pipeline_root_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}

# =========================================================================
# Artifact Registry — Docker images for search-api and training-job
# =========================================================================

resource "google_artifact_registry_repository" "mlops" {
  location      = var.region
  repository_id = var.artifact_repo_id
  format        = "DOCKER"
  description   = "hybrid-search-cloud MLOps container images (api, training job)"
}

# =========================================================================
# Secret Manager — Meilisearch master key
# =========================================================================
#
# 値は Terraform で `random_password` を生成して `secret_version` に流し込む。
# 旧運用は「値を out-of-band で `gcloud secrets versions add` する」だったが、
# Phase 7 PDCA loop (`destroy-all → deploy-all → run-all`) では destroy で
# secret resource ごと消えるため毎回手で再投入が必要になり、deploy-all が
# 一発で完走しない (meili-search Cloud Run が `secret has no enabled
# version` で起動失敗 → search-api → Meilisearch が DNS 失敗で 404)。
# `random_password` で TF が値を所有することで、destroy 後の deploy で
# 自動的に新しいキーが生成され、関連する Cloud Run / ExternalSecret が
# 共通の `latest` を参照する。
#
# Production 化時の切替: `random_password.meili_master_key` を削除し、
# `secret_data` を `gcloud secrets versions add` か Vault などの外部値で
# 上書きする overlay を `environments/prod/` に置く。
resource "random_password" "meili_master_key" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret" "meili_master_key" {
  secret_id = "meili-master-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "meili_master_key" {
  secret      = google_secret_manager_secret.meili_master_key.id
  secret_data = random_password.meili_master_key.result
}

resource "google_secret_manager_secret" "search_api_iap_oauth_client_secret" {
  secret_id = "search-api-iap-oauth-client-secret"
  replication {
    auto {}
  }
}

# Dev-only placeholder version so the ExternalSecret has *something* to read
# while IAP is intentionally disabled in dev (`infra/manifests/policies/search-api-iap-policy.yaml`
# has `iap.enabled: false`). Without this version the ExternalSecret stays in
# `SecretSyncedError` and the GCPBackendPolicy emits `Invalid:
# oauth2ClientSecret cannot be found` even though `iap.enabled: false`
# means LB doesn't actually need the value. PDCA noise reduction only.
#
# Production switch: when `iap.enabled: true`, run
#   `gcloud iap oauth-clients create ...`
# and overwrite this secret via
#   `gcloud secrets versions add search-api-iap-oauth-client-secret --data-file=-`
# before promoting. See docs/runbook/05_運用.md "IAP 有効化".
resource "google_secret_manager_secret_version" "search_api_iap_oauth_client_secret_dev_placeholder" {
  secret      = google_secret_manager_secret.search_api_iap_oauth_client_secret.id
  secret_data = "dev-placeholder-do-not-use-in-prod"
}

# =========================================================================
# IAM — runtime SAs ↔ data resources
# =========================================================================

# sa-api: BQ viewer on mlops dataset (for latest_model_path + retrain queries),
#         BQ viewer on feature_mart (for /search — property_embeddings /
#         properties_cleaned / property_features_daily),
#         storage objectViewer on models bucket, secret accessor.
resource "google_bigquery_dataset_iam_member" "api_mlops_viewer" {
  dataset_id = google_bigquery_dataset.mlops.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_bigquery_dataset_iam_member" "api_feature_viewer" {
  dataset_id = google_bigquery_dataset.feature_mart.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_storage_bucket_iam_member" "api_models_read" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_meili_master_key_access" {
  secret_id = google_secret_manager_secret.meili_master_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_secret_manager_secret_iam_member" "external_secrets_meili_master_key_access" {
  secret_id = google_secret_manager_secret.meili_master_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_accounts.external_secrets.email}"
}

resource "google_secret_manager_secret_iam_member" "external_secrets_search_api_iap_oauth_client_secret_access" {
  secret_id = google_secret_manager_secret.search_api_iap_oauth_client_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_accounts.external_secrets.email}"
}

# sa-job-train: read feature mart, write models + training_runs, read secrets.
resource "google_bigquery_dataset_iam_member" "train_feature_viewer" {
  dataset_id = google_bigquery_dataset.feature_mart.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${var.service_accounts.job_train.email}"
}

resource "google_bigquery_dataset_iam_member" "train_mlops_editor" {
  dataset_id = google_bigquery_dataset.mlops.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.service_accounts.job_train.email}"
}

resource "google_storage_bucket_iam_member" "train_models_admin" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_accounts.job_train.email}"
}

resource "google_storage_bucket_iam_member" "train_pipeline_root_admin" {
  bucket = google_storage_bucket.pipeline_root.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_accounts.job_train.email}"
}

resource "google_secret_manager_secret_iam_member" "job_train_meili_master_key_access" {
  secret_id = google_secret_manager_secret.meili_master_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_accounts.job_train.email}"
}

# sa-job-embed: read raw.properties via feature_mart.properties_cleaned view +
# write feature_mart.property_embeddings + read encoder checkpoints from GCS.
# Kept separate from sa-job-train so the embedding job's IAM blast radius
# excludes ranking_log / feedback_events / training_runs writes.
resource "google_bigquery_dataset_iam_member" "embed_feature_viewer" {
  dataset_id = google_bigquery_dataset.feature_mart.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${var.service_accounts.job_embed.email}"
}

resource "google_bigquery_dataset_iam_member" "embed_feature_editor" {
  dataset_id = google_bigquery_dataset.feature_mart.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.service_accounts.job_embed.email}"
}

resource "google_storage_bucket_iam_member" "embed_models_viewer" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.service_accounts.job_embed.email}"
}

resource "google_bigquery_dataset_iam_member" "pipeline_feature_viewer" {
  dataset_id = google_bigquery_dataset.feature_mart.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${var.service_accounts.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "pipeline_mlops_editor" {
  dataset_id = google_bigquery_dataset.mlops.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.service_accounts.pipeline.email}"
}

resource "google_storage_bucket_iam_member" "pipeline_models_admin" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_accounts.pipeline.email}"
}

resource "google_storage_bucket_iam_member" "pipeline_root_pipeline_admin" {
  bucket = google_storage_bucket.pipeline_root.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_accounts.pipeline.email}"
}

# sa-composer submits PipelineJobs with a local compiled YAML; Vertex / KFP
# stages artifacts under pipeline_root using the caller identity before the
# run switches to sa-pipeline.
resource "google_storage_bucket_iam_member" "pipeline_root_composer_object_admin" {
  bucket = google_storage_bucket.pipeline_root.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_accounts.composer.email}"
}

resource "google_storage_bucket_iam_member" "endpoint_encoder_models_viewer" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.service_accounts.endpoint_encoder.email}"
}

resource "google_storage_bucket_iam_member" "endpoint_reranker_models_viewer" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.service_accounts.endpoint_reranker.email}"
}

# sa-dataform: feature_mart editor.
resource "google_bigquery_dataset_iam_member" "dataform_feature_editor" {
  dataset_id = google_bigquery_dataset.feature_mart.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.service_accounts.dataform.email}"
}

# sa-dataform also runs the property_feature_skew_check Scheduled Query
# (google_bigquery_data_transfer_config in modules/monitoring), which reads
# ranking_log and writes to validation_results — both in the mlops dataset.
resource "google_bigquery_dataset_iam_member" "dataform_mlops_editor" {
  dataset_id = google_bigquery_dataset.mlops.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.service_accounts.dataform.email}"
}

# =========================================================================
# Dataform repository — source for california_housing_features pipeline.
# Optional git_remote_settings: supply dataform_git_token_secret_version to
# auto-sync from GitHub; otherwise the repository is created without remote
# (Dataform UI push / manual sync). The token secret value itself is
# populated out-of-band (see 05_運用.md STEP 10/12).
# =========================================================================

resource "google_dataform_repository" "main" {
  provider = google-beta

  name    = var.dataform_repository_id
  region  = var.region
  project = var.project_id

  # service_account is the identity Dataform uses when executing compiled SQL.
  service_account = var.service_accounts.dataform.email

  dynamic "git_remote_settings" {
    for_each = var.github_repo != "" && var.dataform_git_token_secret_version != "" ? [1] : []
    content {
      url                                 = "https://github.com/${var.github_repo}.git"
      default_branch                      = "main"
      authentication_token_secret_version = var.dataform_git_token_secret_version
    }
  }

  workspace_compilation_overrides {
    default_database = var.project_id
    schema_suffix    = ""
    table_prefix     = ""
  }
}

# Grant sa-dataform the ability to drive this repository (compile / invoke).
resource "google_dataform_repository_iam_member" "admin_self" {
  provider = google-beta

  project    = var.project_id
  region     = var.region
  repository = google_dataform_repository.main.name
  role       = "roles/dataform.admin"
  member     = "serviceAccount:${var.service_accounts.dataform.email}"
}

# Grant the github deployer SA write access so deploy-dataform.yml can
# trigger compilationResults via the Dataform API.
resource "google_dataform_repository_iam_member" "deployer_editor" {
  provider = google-beta

  count = var.github_deployer_sa_email != "" ? 1 : 0

  project    = var.project_id
  region     = var.region
  repository = google_dataform_repository.main.name
  role       = "roles/dataform.editor"
  member     = "serviceAccount:${var.github_deployer_sa_email}"
}
