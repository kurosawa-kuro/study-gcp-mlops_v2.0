output "encoder_endpoint_name" {
  description = "Resolved encoder endpoint resource name placeholder"
  value       = local.encoder_endpoint_name
}

output "reranker_endpoint_name" {
  description = "Resolved reranker endpoint resource name placeholder"
  value       = local.reranker_endpoint_name
}

output "pipeline_root_bucket_name" {
  description = "Vertex pipeline root bucket wired into this module"
  value       = var.pipeline_root_bucket_name
}

output "feature_group_property_features" {
  description = "Canonical property-side feature declarations for the Vertex Feature Group scaffold"
  value       = local.feature_group_property_features
}

output "model_monitoring_alerts_topic" {
  description = "Pub/Sub topic intended for Vertex model monitoring alerts"
  value       = google_pubsub_topic.model_monitoring_alerts
}

output "monitoring_alerts_subscription" {
  description = "BigQuery subscription that persists monitoring alerts into mlops.model_monitoring_alerts"
  value       = google_pubsub_subscription.monitoring_alerts_to_bq
}

output "pipeline_trigger_function_name" {
  description = "Cloud Function name for the Vertex pipeline trigger"
  value       = google_cloudfunctions2_function.pipeline_trigger.name
}

output "pipeline_trigger_eventarc_name" {
  description = "Eventarc trigger name for retrain-to-pipeline wiring"
  value       = google_eventarc_trigger.retrain_to_pipeline.name
}

output "monitoring_trigger_eventarc_name" {
  description = "Eventarc trigger name for monitoring-to-pipeline wiring"
  value       = google_eventarc_trigger.monitoring_to_pipeline.name
}

output "property_features_feature_group" {
  description = "Vertex AI Feature Group wrapping property_features_daily (null when disabled)"
  value = (
    length(google_vertex_ai_feature_group.property_features) > 0
    ? google_vertex_ai_feature_group.property_features[0]
    : null
  )
}

output "feature_online_store_id" {
  description = "Vertex AI Feature Online Store name (= var.feature_online_store_id when enabled, empty string when disabled). Consumed by search-api via VERTEX_FEATURE_ONLINE_STORE_ID env (Wave 1 PR-2 settings)."
  value = (
    length(google_vertex_ai_feature_online_store.property_features) > 0
    ? google_vertex_ai_feature_online_store.property_features[0].name
    : ""
  )
}

output "feature_view_id" {
  description = "Vertex AI Feature View name under the Feature Online Store. Phase 7 固有 = KServe → FOS の **Feature View 経由** opt-in 参照経路で使う。Empty string when disabled. Consumed by search-api via VERTEX_FEATURE_VIEW_ID env."
  value = (
    length(google_vertex_ai_feature_online_store_featureview.property_features) > 0
    ? google_vertex_ai_feature_online_store_featureview.property_features[0].name
    : ""
  )
}

output "feature_online_store_endpoint" {
  description = "Vertex AI Feature Online Store dedicated serving endpoint (regional public endpoint URI). Empty string when disabled. Consumed by search-api via VERTEX_FEATURE_ONLINE_STORE_ENDPOINT env (Wave 1 PR-2 で `endpoint_resolver` seam に渡される)."
  value = (
    length(google_vertex_ai_feature_online_store.property_features) > 0
    ? try(google_vertex_ai_feature_online_store.property_features[0].dedicated_serving_endpoint[0].public_endpoint_domain_name, "")
    : ""
  )
}

output "encoder_endpoint" {
  description = "Vertex AI encoder endpoint resource (null when disabled)"
  value = (
    length(google_vertex_ai_endpoint.encoder) > 0
    ? google_vertex_ai_endpoint.encoder[0]
    : null
  )
}

output "reranker_endpoint" {
  description = "Vertex AI reranker endpoint resource (null when disabled)"
  value = (
    length(google_vertex_ai_endpoint.reranker) > 0
    ? google_vertex_ai_endpoint.reranker[0]
    : null
  )
}
