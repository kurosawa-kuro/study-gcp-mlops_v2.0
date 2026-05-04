# Phase 6 T5 — Cloud Monitoring Service + SLO + burn-rate AlertPolicy.
#
# Phase 5 already ships two log-based alert policies (5xx, p95 latency) via
# module.monitoring. Phase 6 adds *formal SLOs* on top of Cloud Run's built-in
# metrics (run.googleapis.com/request_count + request_latencies) so PMLE-style
# SLI / SLO / Error-Budget / Burn-Rate concepts are learnable against real
# telemetry from the same search-api service.
#
# Design:
#   * One google_monitoring_custom_service anchors both SLOs to the Cloud Run
#     service URI (telemetry.resource_name).
#   * Two google_monitoring_slo:
#       - availability (2xx/total ratio)
#       - latency (fraction of requests under latency_threshold_ms)
#   * Two google_monitoring_alert_policy per SLO (fast + slow burn) using the
#     select_slo_burn_rate() MQL helper. The default multipliers match the
#     Google SRE workbook "Alerting on SLOs" recommendations.
#
# The module takes notification_channel_ids as an input (list) so it can share
# the channel that module.monitoring already creates — no duplicate email
# channel resource here.

locals {
  # Two SLI shapes share the rest of the module; only the filter strings and
  # the telemetry anchor differ. GKE filters use prometheus.googleapis.com
  # metrics exported by PodMonitoring (FastAPI /metrics scrape). Cloud Run
  # filters use the built-in run.googleapis.com/* metrics.
  cluster_location = var.gke_cluster_location != "" ? var.gke_cluster_location : var.region

  telemetry_resource_name_by_type = {
    "k8s_service" = "//container.googleapis.com/projects/${var.project_id}/locations/${local.cluster_location}/clusters/${var.gke_cluster_name}/k8s/namespaces/${var.k8s_namespace}/services/${var.service_name}"
    "cloud_run"   = "//run.googleapis.com/projects/${var.project_id}/locations/${var.region}/services/${var.service_name}"
  }
  telemetry_resource_name = local.telemetry_resource_name_by_type[var.service_type]

  good_filter_by_type = {
    "k8s_service" = <<-EOT
      metric.type="prometheus.googleapis.com/http_requests_total/counter"
      resource.type="prometheus_target"
      resource.label."namespace"="${var.k8s_namespace}"
      metric.label."service"="${var.service_name}"
      metric.label."status"=monitoring.regex.full_match("2..")
    EOT
    "cloud_run"   = <<-EOT
      metric.type="run.googleapis.com/request_count"
      resource.type="cloud_run_revision"
      resource.label."service_name"="${var.service_name}"
      metric.label."response_code_class"="2xx"
    EOT
  }
  good_filter = local.good_filter_by_type[var.service_type]

  total_filter_by_type = {
    "k8s_service" = <<-EOT
      metric.type="prometheus.googleapis.com/http_requests_total/counter"
      resource.type="prometheus_target"
      resource.label."namespace"="${var.k8s_namespace}"
      metric.label."service"="${var.service_name}"
    EOT
    "cloud_run"   = <<-EOT
      metric.type="run.googleapis.com/request_count"
      resource.type="cloud_run_revision"
      resource.label."service_name"="${var.service_name}"
    EOT
  }
  total_filter = local.total_filter_by_type[var.service_type]

  # Latency SLI: GKE → prometheus http_request_duration_seconds histogram
  # exported by FastAPI /metrics (PodMonitoring scrape). Cloud Run → built-in
  # run.googleapis.com/request_latencies distribution (ms).
  latency_filter_by_type = {
    "k8s_service" = <<-EOT
      metric.type="prometheus.googleapis.com/http_request_duration_seconds/histogram"
      resource.type="prometheus_target"
      resource.label."namespace"="${var.k8s_namespace}"
      metric.label."service"="${var.service_name}"
    EOT
    "cloud_run"   = <<-EOT
      metric.type="run.googleapis.com/request_latencies"
      resource.type="cloud_run_revision"
      resource.label."service_name"="${var.service_name}"
    EOT
  }
  latency_filter = local.latency_filter_by_type[var.service_type]

  # prometheus histogram is in seconds, so range.max for GKE must be ms/1000.
  # Cloud Run distribution is already in ms.
  latency_range_max = var.service_type == "k8s_service" ? (var.latency_threshold_ms / 1000.0) : var.latency_threshold_ms
}

resource "google_monitoring_custom_service" "search_api" {
  project      = var.project_id
  service_id   = "${var.service_name}-${var.service_id_suffix}"
  display_name = "${var.service_name} (${var.service_type} SLO anchor)"

  telemetry {
    resource_name = local.telemetry_resource_name
  }
}

# =========================================================================
# Availability SLO — 2xx / total request ratio. Filter source (Cloud Run
# request_count vs Prometheus http_requests_total) is selected by
# var.service_type above.
# =========================================================================

resource "google_monitoring_slo" "availability" {
  project      = var.project_id
  service      = google_monitoring_custom_service.search_api.service_id
  slo_id       = "availability-${replace(format("%.3f", var.availability_goal), ".", "p")}"
  display_name = "Availability ≥ ${format("%.1f%%", var.availability_goal * 100)} over ${var.rolling_period_days}d"

  goal                = var.availability_goal
  rolling_period_days = var.rolling_period_days

  request_based_sli {
    good_total_ratio {
      good_service_filter  = local.good_filter
      total_service_filter = local.total_filter
    }
  }
}

# =========================================================================
# Latency SLO — fraction of requests under latency_threshold_ms. GKE uses
# a Prometheus histogram in seconds (range.max converted above); Cloud Run
# uses the built-in request_latencies distribution (ms).
# =========================================================================

resource "google_monitoring_slo" "latency" {
  project      = var.project_id
  service      = google_monitoring_custom_service.search_api.service_id
  slo_id       = "latency-${var.latency_threshold_ms}ms-${replace(format("%.3f", var.latency_goal), ".", "p")}"
  display_name = "≥ ${format("%.0f%%", var.latency_goal * 100)} of requests < ${var.latency_threshold_ms}ms over ${var.rolling_period_days}d"

  goal                = var.latency_goal
  rolling_period_days = var.rolling_period_days

  request_based_sli {
    distribution_cut {
      distribution_filter = local.latency_filter
      range {
        max = local.latency_range_max
      }
    }
  }
}

# =========================================================================
# Burn-rate alert policies — fast burn (2% of budget in 1h) + slow burn
# (10% of budget in 1d). Multipliers configurable via *_burn_threshold vars.
#
# Phase 6 Run 2 修正: GCP Monitoring は alert policy の
# `condition_threshold.filter` に渡す time window を **24h 以下** に制限する
# (`Durations longer than 24h are not supported`)。Google SRE Workbook の
# 推奨する 3 日窓はそのままでは受理されないので、slow-burn は 24h 窓に縮めて
# 受理可能な最長値を採用している。SLO 本体 (`rolling_period_days = 30`) は
# 不変で、burn-rate の観測窓だけが短くなる。
# =========================================================================

resource "google_monitoring_alert_policy" "availability_fast_burn" {
  project      = var.project_id
  display_name = "${var.service_name} availability SLO fast-burn (${var.fast_burn_threshold}x / 1h)"
  combiner     = "OR"

  conditions {
    display_name = "Fast burn"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.availability.name}\", \"3600s\")"
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.fast_burn_threshold
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
      trigger { count = 1 }
    }
  }

  notification_channels = var.notification_channel_ids
}

resource "google_monitoring_alert_policy" "availability_slow_burn" {
  project      = var.project_id
  display_name = "${var.service_name} availability SLO slow-burn (${var.slow_burn_threshold}x / 1d)"
  combiner     = "OR"

  conditions {
    display_name = "Slow burn"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.availability.name}\", \"86400s\")"
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.slow_burn_threshold
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
      trigger { count = 1 }
    }
  }

  notification_channels = var.notification_channel_ids
}

resource "google_monitoring_alert_policy" "latency_fast_burn" {
  project      = var.project_id
  display_name = "${var.service_name} latency SLO fast-burn (${var.fast_burn_threshold}x / 1h)"
  combiner     = "OR"

  conditions {
    display_name = "Fast burn"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.latency.name}\", \"3600s\")"
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.fast_burn_threshold
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
      trigger { count = 1 }
    }
  }

  notification_channels = var.notification_channel_ids
}

resource "google_monitoring_alert_policy" "latency_slow_burn" {
  project      = var.project_id
  display_name = "${var.service_name} latency SLO slow-burn (${var.slow_burn_threshold}x / 1d)"
  combiner     = "OR"

  conditions {
    display_name = "Slow burn"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.latency.name}\", \"86400s\")"
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.slow_burn_threshold
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
      trigger { count = 1 }
    }
  }

  notification_channels = var.notification_channel_ids
}
