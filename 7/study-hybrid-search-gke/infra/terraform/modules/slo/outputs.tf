output "service_id" {
  description = "google_monitoring_custom_service service_id anchoring both SLOs. Use this to look up SLOs via the Monitoring REST API."
  value       = google_monitoring_custom_service.search_api.service_id
}

output "service_full_name" {
  description = "Full resource name (projects/.../services/...) of the custom service, usable in select_slo_burn_rate() queries from ad-hoc Monitoring dashboards."
  value       = google_monitoring_custom_service.search_api.name
}

output "availability_slo_name" {
  description = "Full resource name of the availability SLO (projects/.../services/.../serviceLevelObjectives/...). Needed for external tooling like `gcloud monitoring slos describe`."
  value       = google_monitoring_slo.availability.name
}

output "latency_slo_name" {
  description = "Full resource name of the latency SLO."
  value       = google_monitoring_slo.latency.name
}

output "alert_policy_ids" {
  description = "Map of SLO burn-rate alert policy IDs keyed by (slo, burn speed). Handy for automation that wants to silence specific policies."
  value = {
    availability_fast_burn = google_monitoring_alert_policy.availability_fast_burn.id
    availability_slow_burn = google_monitoring_alert_policy.availability_slow_burn.id
    latency_fast_burn      = google_monitoring_alert_policy.latency_fast_burn.id
    latency_slow_burn      = google_monitoring_alert_policy.latency_slow_burn.id
  }
}
