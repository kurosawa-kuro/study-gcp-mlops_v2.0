# Phase 5 — log-based metrics, alert policies, + mean-drift Scheduled Query.

# =========================================================================
# Log-based metrics
# =========================================================================

resource "google_logging_metric" "api_error_rate" {
  name        = "search_api_5xx"
  description = "Count of 5xx responses from search-api (structured access logs)"
  filter      = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="search-api"
    severity>=ERROR
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "api_p95_latency" {
  name            = "search_api_latency_ms"
  description     = "Distribution of request latency from search-api (extracted from access logs)"
  filter          = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="search-api"
    jsonPayload.message="request completed"
    jsonPayload.latency_ms:*
  EOT
  value_extractor = "EXTRACT(jsonPayload.latency_ms)"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"
  }

  bucket_options {
    exponential_buckets {
      num_finite_buckets = 24
      growth_factor      = 2
      scale              = 1
    }
  }
}

# =========================================================================
# Notification channel — email supplied via var.oncall_email
# (env/config/setting.yaml::oncall_email).
# =========================================================================

resource "google_monitoring_notification_channel" "email" {
  display_name = "hybrid-search-cloud oncall email"
  type         = "email"
  labels = {
    email_address = var.oncall_email
  }
  force_delete = false
}

# =========================================================================
# Alert policies
#
# GCP's Monitoring API needs up to ~60s to index a freshly-created
# log-based metric before alert policies can reference it ("Cannot find
# metric(s) that match type = ..."). `time_sleep` forces Terraform to
# wait between the metric create and the alert policy create, eliminating
# the race on first apply.
# =========================================================================

resource "time_sleep" "wait_for_log_metric_indexing" {
  triggers = {
    metrics = sha256(jsonencode({
      api_error_rate = {
        name   = google_logging_metric.api_error_rate.name
        filter = trimspace(google_logging_metric.api_error_rate.filter)
      }
      api_p95_latency = {
        name            = google_logging_metric.api_p95_latency.name
        filter          = trimspace(google_logging_metric.api_p95_latency.filter)
        value_extractor = google_logging_metric.api_p95_latency.value_extractor
      }
    }))
  }
  depends_on = [
    google_logging_metric.api_error_rate,
    google_logging_metric.api_p95_latency,
  ]
  create_duration = "90s"
}

resource "google_monitoring_alert_policy" "api_error_rate" {
  display_name = "search-api 5xx > 1% over 10m"
  combiner     = "OR"

  conditions {
    display_name = "5xx count"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.api_error_rate.name}\" AND resource.type=\"cloud_run_revision\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
      trigger { count = 1 }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  depends_on = [time_sleep.wait_for_log_metric_indexing]
}

resource "google_monitoring_alert_policy" "api_p95_latency" {
  display_name = "search-api p95 latency > 500ms over 10m"
  combiner     = "OR"

  conditions {
    display_name = "p95 latency"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.api_p95_latency.name}\" AND resource.type=\"cloud_run_revision\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 500
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MEAN"
      }
      trigger { count = 1 }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  depends_on = [time_sleep.wait_for_log_metric_indexing]
}

# =========================================================================
# Scheduled Query — ranker feature skew check (daily JST 05:00).
#
# Phase 10c removed: ``california_housing_skew_check`` transfer config.
# Operators on an existing project must delete the old transfer via
# ``bq rm --transfer_config <name>`` *before* the next ``terraform apply``,
# otherwise the destroy leaves the config orphaned. See ``docs/runbook/05_運用.md
# §3.9`` for the full migration checklist.
# =========================================================================

resource "google_bigquery_data_transfer_config" "property_feature_skew_check" {
  display_name           = "property_feature_skew_check"
  data_source_id         = "scheduled_query"
  destination_dataset_id = var.mlops_dataset_id
  location               = var.region
  schedule               = "every day 05:00"
  # DTS requires either `version_info` (OAuth code, only works for user identities)
  # or `service_account_name` (SA delegation). sa-dataform already has
  # bigquery.jobUser on the project + dataEditor on feature_mart and mlops.
  service_account_name = var.service_accounts.dataform.email
  schedule_options {
    disable_auto_scheduling = false
  }
  params = {
    query = file(var.ranker_skew_sql_path)
  }
}

resource "google_bigquery_data_transfer_config" "model_output_drift_check" {
  display_name           = "model_output_drift_check"
  data_source_id         = "scheduled_query"
  destination_dataset_id = var.mlops_dataset_id
  location               = var.region
  schedule               = "every day 05:10"
  service_account_name   = var.service_accounts.dataform.email
  schedule_options {
    disable_auto_scheduling = false
  }
  params = {
    query = file(var.model_output_drift_sql_path)
  }
}
