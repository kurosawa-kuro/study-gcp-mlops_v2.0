output "mlops_dataset" {
  value = google_bigquery_dataset.mlops
}

output "feature_mart_dataset" {
  value = google_bigquery_dataset.feature_mart
}

output "predictions_dataset" {
  value = google_bigquery_dataset.predictions
}

output "training_runs_table" {
  value = google_bigquery_table.training_runs
}

output "validation_results_table" {
  value = google_bigquery_table.validation_results
}

output "model_monitoring_alerts_table" {
  value = google_bigquery_table.model_monitoring_alerts
}

output "property_features_daily_table" {
  value = google_bigquery_table.property_features_daily
}

output "property_features_online_latest_table" {
  value = google_bigquery_table.property_features_online_latest
}

output "property_embeddings_table" {
  value = google_bigquery_table.property_embeddings
}

output "search_logs_table" {
  value = google_bigquery_table.search_logs
}

output "ranking_log_table" {
  value = google_bigquery_table.ranking_log
}

output "feedback_events_table" {
  value = google_bigquery_table.feedback_events
}

# Phase 6 T2 — Dataflow streaming aggregate sink.
output "ranking_log_hourly_ctr_table" {
  value = google_bigquery_table.ranking_log_hourly_ctr
}

output "models_bucket" {
  value = google_storage_bucket.models
}

output "artifacts_bucket" {
  value = google_storage_bucket.artifacts
}

output "pipeline_root_bucket" {
  value = google_storage_bucket.pipeline_root
}

output "artifact_registry" {
  value = google_artifact_registry_repository.mlops
}

output "secrets" {
  value = {
    meili_master_key                   = google_secret_manager_secret.meili_master_key
    search_api_iap_oauth_client_secret = google_secret_manager_secret.search_api_iap_oauth_client_secret
  }
}

output "dataform_repository" {
  description = "google_dataform_repository.main — name is referenced by .github/workflows/deploy-dataform.yml"
  value       = google_dataform_repository.main
}
