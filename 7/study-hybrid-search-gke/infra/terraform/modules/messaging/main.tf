# =========================================================================
# messaging module — Pub/Sub + Scheduler (API is served from GKE, not Cloud Run)
#
# Phase 5 の Cloud Run Service (search-api) はこのモジュールから抜けた。
# Phase 6 では search-api は GKE に載るため、Cloud Run 関連リソースはここには
# 置かない。Scheduler は GKE Gateway 経由で /jobs/check-retrain を叩く。
# =========================================================================

data "google_project" "current" {}

resource "google_pubsub_topic" "ranking_log" {
  name = "ranking-log"
}

resource "google_pubsub_topic" "search_feedback" {
  name = "search-feedback"
}

resource "google_pubsub_topic" "retrain_trigger" {
  name = "retrain-trigger"
}

resource "google_pubsub_topic_iam_member" "api_publish_ranking_log" {
  topic  = google_pubsub_topic.ranking_log.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_pubsub_topic_iam_member" "api_publish_feedback" {
  topic  = google_pubsub_topic.search_feedback.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_pubsub_topic_iam_member" "api_publish_retrain" {
  topic  = google_pubsub_topic.retrain_trigger.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${var.service_accounts.api.email}"
}

resource "google_pubsub_topic_iam_member" "scheduler_publish_retrain" {
  topic  = google_pubsub_topic.retrain_trigger.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${var.service_accounts.scheduler.email}"
}

resource "google_pubsub_subscription" "ranking_log_to_bq" {
  name  = "ranking-log-to-bq"
  topic = google_pubsub_topic.ranking_log.name

  bigquery_config {
    table               = "${var.project_id}.${var.mlops_dataset_id}.${var.ranking_log_table_id}"
    use_table_schema    = true
    drop_unknown_fields = true
    write_metadata      = false
  }

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  depends_on = [
    google_project_iam_member.pubsub_bq_writer,
    google_project_iam_member.pubsub_bq_metadata_viewer,
  ]
}

resource "google_pubsub_subscription" "search_feedback_to_bq" {
  name  = "search-feedback-to-bq"
  topic = google_pubsub_topic.search_feedback.name

  bigquery_config {
    table               = "${var.project_id}.${var.mlops_dataset_id}.${var.feedback_events_table_id}"
    use_table_schema    = true
    drop_unknown_fields = true
    write_metadata      = false
  }

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  depends_on = [
    google_project_iam_member.pubsub_bq_writer,
    google_project_iam_member.pubsub_bq_metadata_viewer,
  ]
}

locals {
  pubsub_service_agent = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "pubsub_bq_writer" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = local.pubsub_service_agent
}

resource "google_project_iam_member" "pubsub_bq_metadata_viewer" {
  project = var.project_id
  role    = "roles/bigquery.metadataViewer"
  member  = local.pubsub_service_agent
}

# =========================================================================
# **[Phase 7 W2-4 Stage 3 で smoke / 比較教材用に格下げ]**
#
# 本線 retrain schedule は Cloud Composer `retrain_orchestration` DAG
# (schedule "0 19 * * *" UTC = 04:00 JST、本 phase canonical = docs/01 §3.6)。
# 本 Cloud Scheduler は本線から外れた **smoke / 軽量代替経路** として残置。
# schedule は月 1 回 04:00 JST に格下げし、dead-trigger 化を防ぐ最小頻度で
# 「Composer 経由 vs Cloud Scheduler 直叩き」の比較教材として動く状態を
# 維持する。リソース削除はしない (Phase 4-5 派生時に再導入されるため)。
# =========================================================================
resource "google_cloud_scheduler_job" "check_retrain_daily" {
  count = var.api_external_url == "" ? 0 : 1

  name        = "check-retrain-daily"
  description = "[smoke / 軽量代替] POST /jobs/check-retrain (本線 retrain は Composer DAG retrain_orchestration、本 trigger は月 1 回 smoke のみ)"
  schedule    = "0 4 1 * *"
  time_zone   = "Asia/Tokyo"
  region      = var.region

  http_target {
    http_method = "POST"
    uri         = "${var.api_external_url}/jobs/check-retrain"

    oidc_token {
      service_account_email = var.service_accounts.scheduler.email
      audience              = var.api_external_url
    }
  }

  retry_config {
    retry_count          = 1
    max_retry_duration   = "120s"
    min_backoff_duration = "30s"
  }
}
