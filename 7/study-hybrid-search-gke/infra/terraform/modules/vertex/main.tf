locals {
  # Feature Group parity invariant:
  # - ml/data/feature_engineering/schema.py::FEATURE_COLS_RANKER (property-side 7 cols)
  # - infra/sql/monitoring/validate_feature_skew.sql UNPIVOT lists
  # - tests/integration/parity/test_feature_parity_feature_group.py
  #
  # Query-time signals (me5_score / lexical_rank / semantic_rank) are excluded.
  feature_group_property_features = [
    {
      name        = "rent"
      value_type  = "DOUBLE"
      description = "Monthly rent"
    },
    {
      name        = "walk_min"
      value_type  = "DOUBLE"
      description = "Walking minutes to nearest station"
    },
    {
      name        = "age_years"
      value_type  = "DOUBLE"
      description = "Property age in years"
    },
    {
      name        = "area_m2"
      value_type  = "DOUBLE"
      description = "Floor area in square meters"
    },
    {
      name        = "ctr"
      value_type  = "DOUBLE"
      description = "Historical click-through rate"
    },
    {
      name        = "fav_rate"
      value_type  = "DOUBLE"
      description = "Historical favorite rate"
    },
    {
      name        = "inquiry_rate"
      value_type  = "DOUBLE"
      description = "Historical inquiry conversion rate"
    },
  ]

  encoder_endpoint_name = (
    var.encoder_endpoint_id != ""
    ? var.encoder_endpoint_id
    : "projects/${var.project_id}/locations/${var.vertex_location}/endpoints/${var.encoder_endpoint_display_name}"
  )
  reranker_endpoint_name = (
    var.reranker_endpoint_id != ""
    ? var.reranker_endpoint_id
    : "projects/${var.project_id}/locations/${var.vertex_location}/endpoints/${var.reranker_endpoint_display_name}"
  )
  pipeline_trigger_function_name   = "pipeline-trigger"
  pipeline_trigger_eventarc_name   = "retrain-to-pipeline"
  monitoring_trigger_eventarc_name = "monitoring-to-pipeline"
  pubsub_service_agent             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  pipeline_template_uri            = "gs://${var.pipeline_root_bucket_name}/templates/property-search-train.yaml"
  pipeline_root_uri                = "gs://${var.pipeline_root_bucket_name}/runs"
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_pubsub_topic" "model_monitoring_alerts" {
  name = "model-monitoring-alerts"
}

resource "google_bigquery_dataset_iam_member" "pubsub_mlops_editor" {
  dataset_id = var.mlops_dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = local.pubsub_service_agent
}

resource "google_bigquery_dataset_iam_member" "pubsub_mlops_metadata_viewer" {
  dataset_id = var.mlops_dataset_id
  role       = "roles/bigquery.metadataViewer"
  member     = local.pubsub_service_agent
}

resource "google_pubsub_subscription" "monitoring_alerts_to_bq" {
  name  = "monitoring-alerts-to-bq"
  topic = google_pubsub_topic.model_monitoring_alerts.name

  bigquery_config {
    table               = "${var.project_id}.${var.mlops_dataset_id}.${var.model_monitoring_alerts_table_id}"
    use_table_schema    = true
    drop_unknown_fields = true
    write_metadata      = false
  }

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  depends_on = [
    google_bigquery_dataset_iam_member.pubsub_mlops_editor,
    google_bigquery_dataset_iam_member.pubsub_mlops_metadata_viewer,
  ]
}

data "archive_file" "pipeline_trigger_source" {
  type        = "zip"
  source_dir  = "${path.module}/../../../../pipeline/workflow/trigger_zip"
  output_path = "${path.module}/.pipeline-trigger.zip"
}

resource "google_storage_bucket_object" "pipeline_trigger_zip" {
  name   = "functions/pipeline-trigger-${data.archive_file.pipeline_trigger_source.output_md5}.zip"
  bucket = var.pipeline_root_bucket_name
  source = data.archive_file.pipeline_trigger_source.output_path
}

# =========================================================================
# **[Phase 7 W2-4 Stage 3 で smoke / 軽量代替経路として残置]**
#
# 本線 retrain trigger は Cloud Composer `retrain_orchestration` DAG
# (canonical = docs/01 §3 / §3.6)。本 Cloud Function + Eventarc 2 本は
# Pub/Sub `retrain-trigger` topic から Vertex Pipelines を直接叩く軽量代替
# 経路として残置 (Composer 経由 vs Pub/Sub 直叩きの比較教材)。
#
# リソース削除はしない (Phase 4-5 派生時に再導入されるため)。
# 本線重複防止のため、同一 retrain job を 2 経路から起動しないことが契約。
# =========================================================================
resource "google_cloudfunctions2_function" "pipeline_trigger" {
  provider = google-beta

  name     = local.pipeline_trigger_function_name
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "trigger_pipeline"

    source {
      storage_source {
        bucket = var.pipeline_root_bucket_name
        object = google_storage_bucket_object.pipeline_trigger_zip.name
      }
    }
  }

  service_config {
    available_memory      = "256M"
    timeout_seconds       = 60
    service_account_email = var.service_accounts.pipeline_trigger.email

    environment_variables = {
      PROJECT_ID               = var.project_id
      VERTEX_LOCATION          = var.vertex_location
      PIPELINE_TEMPLATE_URI    = local.pipeline_template_uri
      PIPELINE_ROOT            = local.pipeline_root_uri
      PIPELINE_SERVICE_ACCOUNT = var.service_accounts.pipeline.email
      PIPELINE_ENABLE_CACHING  = "false"
      PIPELINE_LABELS          = jsonencode({ component = "pipeline-trigger", managed_by = "terraform" })
    }
  }
}

resource "google_cloud_run_service_iam_member" "pipeline_trigger_invoker" {
  location = var.region
  service  = google_cloudfunctions2_function.pipeline_trigger.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_accounts.pipeline_trigger.email}"
}

resource "google_eventarc_trigger" "retrain_to_pipeline" {
  provider = google-beta

  name     = local.pipeline_trigger_eventarc_name
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  transport {
    pubsub {
      topic = var.retrain_trigger_topic_id
    }
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.pipeline_trigger.name
      region  = var.region
      path    = "/"
    }
  }

  service_account = var.service_accounts.pipeline_trigger.email

  depends_on = [
    google_cloudfunctions2_function.pipeline_trigger,
    google_cloud_run_service_iam_member.pipeline_trigger_invoker,
  ]
}

resource "google_eventarc_trigger" "monitoring_to_pipeline" {
  provider = google-beta

  name     = local.monitoring_trigger_eventarc_name
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.model_monitoring_alerts.id
    }
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.pipeline_trigger.name
      region  = var.region
      path    = "/"
    }
  }

  service_account = var.service_accounts.pipeline_trigger.email

  depends_on = [
    google_cloudfunctions2_function.pipeline_trigger,
    google_cloud_run_service_iam_member.pipeline_trigger_invoker,
  ]
}

# =========================================================================
# Vertex AI Feature Group — offline wrapper over feature_mart.property_features_daily.
#
# Entity: property_id. Seven property-side features mirror FEATURE_COLS_RANKER
# (parity test: tests/parity/test_feature_parity_feature_group.py).
# Query-time signals (me5_score / lexical_rank / semantic_rank) stay outside
# the Feature Group because they are computed per-request, not per-property.
# =========================================================================

resource "google_vertex_ai_feature_group" "property_features" {
  count    = var.enable_feature_group ? 1 : 0
  provider = google-beta

  name        = "property_features"
  region      = var.vertex_location
  description = "Offline Feature Group wrapping feature_mart.property_features_daily"

  big_query {
    big_query_source {
      input_uri = "bq://${var.project_id}.${var.feature_mart_dataset_id}.property_features_daily"
    }
    entity_id_columns = ["property_id"]
  }
}

resource "google_vertex_ai_feature_group_feature" "property_features" {
  for_each = var.enable_feature_group ? {
    for feat in local.feature_group_property_features : feat.name => feat
  } : {}

  provider = google-beta

  name          = each.value.name
  region        = var.vertex_location
  feature_group = google_vertex_ai_feature_group.property_features[0].name
  description   = each.value.description
}

# =========================================================================
# Feature Online Store + FeatureView — Phase 7 で追加。
# `vertex_feature_group.py` script が `FetchFeatureValuesRequest` で
# 1 entity の最新 feature 値を引くために必要。Feature Group (offline、上)
# だけでは online fetch endpoint が立たないので 501 Not Implemented になる。
#
# Optimized 種別 (= node count 自動スケール、課金は読み込みクエリ単位)を
# 採用。学習リポでは常駐 sync が走り続けるのは過剰なので
# `enable_feature_online_store` フラグで gate し、必要時のみ apply する。
# =========================================================================

resource "google_vertex_ai_feature_online_store" "property_features" {
  count    = var.enable_feature_online_store ? 1 : 0
  provider = google-beta

  name   = var.feature_online_store_id
  region = var.vertex_location

  optimized {}

  # 学習リポなので公開は不要 (Pod から VPC 経由で fetch する)。
  dedicated_serving_endpoint {
    private_service_connect_config {
      enable_private_service_connect = false
    }
  }

  # Optimized stores reject UpdateFeatureOnlineStore; Terraform must not
  # attempt to "fix" drift on dedicated_serving_endpoint (async
  # publicEndpointDomainName). That left terraform output empty — deploy
  # resolves the live host via Vertex REST GET in `configmap_overlay.py`.
  lifecycle {
    ignore_changes = [
      optimized,
      dedicated_serving_endpoint,
      labels,
    ]
  }
}

# FeatureView は online serving の実体。Run 2 の live 検証では
# `feature_registry_source` 経由だと sync 完了後も entity lookup が 404
# のまま残ったため、Wave 2 では online serving contract を優先して
# BigQuery source を直接 materialize する形に固定する。
#
# Feature Group / Feature resources 自体は別目的で残す:
# - Feature Registry の canonical schema 宣言
# - feature parity invariant
# - 将来の monitoring / catalog 用メタデータ
resource "google_vertex_ai_feature_online_store_featureview" "property_features" {
  count    = var.enable_feature_online_store ? 1 : 0
  provider = google-beta

  name                 = var.feature_view_id
  region               = var.vertex_location
  feature_online_store = google_vertex_ai_feature_online_store.property_features[0].name

  big_query_source {
    uri = "bq://${var.project_id}.${var.feature_mart_dataset_id}.property_features_online_latest"
    entity_id_columns = ["property_id"]
  }

  # 学習リポ: 1 hour ごとに sync (cron)。実運用なら Dataflow streaming や
  # `manual` sync (= API 経由で都度トリガ) も選択可。
  sync_config {
    cron = "0 * * * *"
  }
}

# =========================================================================
# Vertex AI Endpoints — empty shells. Model deployment is handled by the
# Python SDK (register_reranker KFP component + scripts/setup/create_*.py)
# because traffic-split / deployed_model nesting in Terraform is immature.
# =========================================================================

resource "google_vertex_ai_endpoint" "encoder" {
  count = var.enable_vertex_endpoint_shell ? 1 : 0

  name         = "property-encoder-endpoint"
  display_name = var.encoder_endpoint_display_name
  description  = "Vertex AI endpoint hosting the multilingual-e5-base encoder"
  location     = var.vertex_location
  project      = var.project_id
}

# Model deployments (aiplatform.Model.deploy) mutate the endpoints'
# deployed_models / traffic_split server-side; the provider surfaces these as
# computed fields so we leave them out of the managed resource entirely.

resource "google_vertex_ai_endpoint" "reranker" {
  count = var.enable_vertex_endpoint_shell ? 1 : 0

  name         = "property-reranker-endpoint"
  display_name = var.reranker_endpoint_display_name
  description  = "Vertex AI endpoint hosting the LightGBM LambdaRank reranker"
  location     = var.vertex_location
  project      = var.project_id
}

resource "google_storage_bucket_iam_member" "endpoint_encoder_models_reader" {
  bucket = var.models_bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.service_accounts.endpoint_encoder.email}"
}

resource "google_storage_bucket_iam_member" "endpoint_reranker_models_reader" {
  bucket = var.models_bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.service_accounts.endpoint_reranker.email}"
}
