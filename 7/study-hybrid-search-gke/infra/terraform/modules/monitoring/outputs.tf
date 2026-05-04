output "notification_channel_id" {
  value = google_monitoring_notification_channel.email.id
}

output "ranker_skew_check_config_id" {
  value = google_bigquery_data_transfer_config.property_feature_skew_check.id
}

output "model_output_drift_check_config_id" {
  value = google_bigquery_data_transfer_config.model_output_drift_check.id
}
