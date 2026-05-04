output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "models_bucket" {
  value = module.data.models_bucket.name
}

output "pipeline_root_bucket" {
  description = "GCS bucket used as Vertex AI pipeline root"
  value       = module.data.pipeline_root_bucket.name
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${module.data.artifact_registry.repository_id}"
}

output "training_runs_table" {
  value = "${var.project_id}.${module.data.mlops_dataset.dataset_id}.${module.data.training_runs_table.table_id}"
}

output "ranking_log_table" {
  value = "${var.project_id}.${module.data.mlops_dataset.dataset_id}.${module.data.ranking_log_table.table_id}"
}

output "feedback_events_table" {
  value = "${var.project_id}.${module.data.mlops_dataset.dataset_id}.${module.data.feedback_events_table.table_id}"
}

output "model_monitoring_alerts_table" {
  description = "BigQuery sink for Vertex model monitoring alerts"
  value       = "${var.project_id}.${module.data.mlops_dataset.dataset_id}.${module.data.model_monitoring_alerts_table.table_id}"
}

output "ranking_log_topic" {
  value = module.messaging.ranking_log_topic.name
}

output "search_feedback_topic" {
  value = module.messaging.search_feedback_topic.name
}

output "retrain_trigger_topic" {
  value = module.messaging.retrain_trigger_topic.name
}

output "service_accounts" {
  value = {
    api               = module.iam.service_accounts.api.email
    job_train         = module.iam.service_accounts.job_train.email
    job_embed         = module.iam.service_accounts.job_embed.email
    dataform          = module.iam.service_accounts.dataform.email
    scheduler         = module.iam.service_accounts.scheduler.email
    pipeline          = module.iam.service_accounts.pipeline.email
    endpoint_encoder  = module.iam.service_accounts.endpoint_encoder.email
    endpoint_reranker = module.iam.service_accounts.endpoint_reranker.email
    pipeline_trigger  = module.iam.service_accounts.pipeline_trigger.email
    external_secrets  = module.iam.service_accounts.external_secrets.email
  }
}

output "vertex_encoder_endpoint_name" {
  description = "Resolved Vertex encoder endpoint resource name placeholder"
  value       = module.vertex.encoder_endpoint_name
}

output "vertex_reranker_endpoint_name" {
  description = "Resolved Vertex reranker endpoint resource name placeholder"
  value       = module.vertex.reranker_endpoint_name
}

output "vertex_feature_group_property_features" {
  description = "Canonical property-side feature declarations for the Vertex Feature Group scaffold"
  value       = module.vertex.feature_group_property_features
}

# =========================================================================
# Vertex AI Vector Search (Phase 7 Wave 2 W2-1) — search-api ConfigMap (W2-5) と
# embed pipeline VVS upsert step (Wave 1 PR-3) が outputs を参照する。
# =========================================================================

output "vertex_feature_online_store_id" {
  description = "Vertex AI Feature Online Store name. Empty string when enable_feature_online_store=false. Consumed by search-api via VERTEX_FEATURE_ONLINE_STORE_ID env."
  value       = module.vertex.feature_online_store_id
}

output "vertex_feature_view_id" {
  description = "Vertex AI Feature View name. Phase 7 固有 = KServe → FOS の Feature View 経由 opt-in 参照経路。Empty string when disabled. Consumed by search-api via VERTEX_FEATURE_VIEW_ID env."
  value       = module.vertex.feature_view_id
}

output "vertex_feature_online_store_endpoint" {
  description = "Vertex AI Feature Online Store regional public endpoint URI (Feature View 経由 fetch のため). Empty when disabled. Consumed by search-api via VERTEX_FEATURE_ONLINE_STORE_ENDPOINT env."
  value       = module.vertex.feature_online_store_endpoint
}

output "vector_search_index_endpoint_id" {
  description = "Vertex AI Vector Search index endpoint resource name. Empty string when enable_vector_search=false. Consumed by search-api via VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT_ID env."
  value       = module.vector_search.index_endpoint_id
}

output "vector_search_deployed_index_id" {
  description = "Vertex AI Vector Search deployed index ID. Empty string when disabled. Consumed by search-api via VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID env."
  value       = module.vector_search.deployed_index_id
}

output "vector_search_index_resource_name" {
  description = "Vertex AI Vector Search index resource name (full path). Empty string when disabled. Consumed by embed pipeline VVS upsert step via vector_search_index_resource_name KFP param."
  value       = module.vector_search.index_resource_name
}

output "model_monitoring_alerts_topic" {
  description = "Pub/Sub topic for Vertex model monitoring alerts"
  value       = module.vertex.model_monitoring_alerts_topic.name
}

output "model_monitoring_alerts_subscription" {
  description = "BigQuery subscription for Vertex model monitoring alerts"
  value       = module.vertex.monitoring_alerts_subscription.name
}

output "model_output_drift_check_config_id" {
  description = "Scheduled Query config ID for the self-managed KServe drift substitute"
  value       = module.monitoring.model_output_drift_check_config_id
}

output "pipeline_trigger_function_name" {
  description = "Reserved Cloud Function name for the Vertex pipeline trigger"
  value       = module.vertex.pipeline_trigger_function_name
}

output "pipeline_trigger_eventarc_name" {
  description = "Reserved Eventarc trigger name for retrain-to-pipeline wiring"
  value       = module.vertex.pipeline_trigger_eventarc_name
}

output "monitoring_trigger_eventarc_name" {
  description = "Eventarc trigger name for monitoring-to-pipeline wiring"
  value       = module.vertex.monitoring_trigger_eventarc_name
}

output "workload_identity_provider" {
  description = "Register as GitHub Actions var WORKLOAD_IDENTITY_PROVIDER"
  value       = module.iam.workload_identity_provider
}

output "github_deployer_sa_email" {
  description = "Register as GitHub Actions var DEPLOYER_SERVICE_ACCOUNT"
  value       = module.iam.github_deployer_sa_email
}

output "dataform_repository_name" {
  description = "Dataform repository name — matches env.REPOSITORY in .github/workflows/deploy-dataform.yml"
  value       = module.data.dataform_repository.name
}

output "meili_base_url" {
  description = "Cloud Run URL of meili-search service"
  value       = module.meilisearch.meili_base_url
}

output "meili_data_bucket" {
  description = "GCS bucket mounted by meili-search"
  value       = module.meilisearch.meili_data_bucket.name
}

output "gke_cluster_name" {
  description = "GKE Autopilot cluster name"
  value       = module.gke.cluster_name
}

output "gke_cluster_location" {
  description = "GKE Autopilot cluster location"
  value       = module.gke.cluster_location
}

output "kserve_search_namespace" {
  description = "Namespace hosting search-api"
  value       = module.kserve.search_namespace
}

output "kserve_inference_namespace" {
  description = "Namespace hosting KServe InferenceService resources"
  value       = module.kserve.inference_namespace
}

# Phase 7 W2-4: Cloud Composer outputs — consumed by
# `scripts/deploy/composer_deploy_dags.py` (DAG bucket) and
# `make ops-composer-trigger` / `ops-composer-list-runs` smoke targets.
output "composer_dag_bucket" {
  description = "GCS prefix Composer reads DAGs from. Consumed by `make composer-deploy-dags`. Empty when `enable_composer=false`."
  value       = module.composer.dag_bucket
}

output "composer_airflow_uri" {
  description = "Airflow UI URL of the Composer environment. Used by `make ops-composer-list-runs`."
  value       = module.composer.airflow_uri
}

output "composer_environment_name" {
  description = "Composer environment name (used by `gcloud composer environments run --environment=<name>`)."
  value       = module.composer.environment_name
}
