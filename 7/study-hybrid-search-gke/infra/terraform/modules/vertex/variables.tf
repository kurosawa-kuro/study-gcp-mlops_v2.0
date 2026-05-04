variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Primary region for regional resources"
  type        = string
}

variable "vertex_location" {
  description = "Vertex AI location for endpoints and pipelines"
  type        = string
}

variable "service_accounts" {
  description = "Map of SA resources emitted by the iam module. Reserved for future Vertex resources."
  type        = any
}

variable "mlops_dataset_id" {
  description = "BQ dataset ID for mlops tables"
  type        = string
}

variable "feature_mart_dataset_id" {
  description = "BQ dataset ID for feature mart tables"
  type        = string
}

variable "pipeline_root_bucket_name" {
  description = "GCS bucket name used as Vertex AI pipeline root"
  type        = string
}

variable "model_monitoring_alerts_table_id" {
  description = "BigQuery table ID used as the sink for Vertex model monitoring alerts"
  type        = string
}

variable "encoder_endpoint_id" {
  description = "Vertex AI encoder endpoint ID or full resource name. Empty string keeps the module in scaffold mode."
  type        = string
  default     = ""
}

variable "reranker_endpoint_id" {
  description = "Vertex AI reranker endpoint ID or full resource name. Empty string keeps the module in scaffold mode."
  type        = string
  default     = ""
}

variable "encoder_endpoint_display_name" {
  description = "Display name reserved for the encoder endpoint"
  type        = string
}

variable "reranker_endpoint_display_name" {
  description = "Display name reserved for the reranker endpoint"
  type        = string
}

variable "retrain_trigger_topic_id" {
  description = "Pub/Sub topic ID for retrain-trigger events emitted by search-api"
  type        = string
}

variable "retrain_trigger_topic_name" {
  description = "Pub/Sub topic name for retrain-trigger events emitted by search-api"
  type        = string
}

variable "models_bucket_name" {
  description = "GCS bucket name hosting model artifacts read by Vertex endpoints"
  type        = string
}

variable "enable_feature_group" {
  description = "When true, declare the Vertex AI Feature Group wrapping feature_mart.property_features_daily"
  type        = bool
  default     = true
}

variable "enable_feature_online_store" {
  description = "When true, declare the Vertex AI Feature Online Store + FeatureView so search-api / KServe pods can fetch featureValues via Feature View 経由 (training-serving skew prevention). Phase 7 Wave 2 W2-2 で default を true に flip — Phase 5 必須要素として canonical (本 phase docs/01 §0)。`mlops-dev-a` PDCA でコストを抑えたいときは terraform.tfvars で false に override 可能。"
  type        = bool
  default     = true
}

variable "feature_online_store_id" {
  description = "Vertex AI Feature Online Store name. Must match VERTEX_FEATURE_ONLINE_STORE_ID env consumed by search-api (Wave 1 PR-2 で settings 化済) と scripts/ops/vertex/feature_group.py."
  type        = string
  default     = "mlops_dev_feature_store"
}

variable "feature_view_id" {
  description = "Vertex AI Feature View name (under the Online Store) that wraps the property_features Feature Group. Phase 7 固有 = KServe pod から **Feature View 経由で** Feature Online Store を opt-in 参照する経路 (本 phase docs/01 §0)。Must match VERTEX_FEATURE_VIEW_ID env consumed by search-api adapter (FeatureOnlineStoreFetcher)."
  type        = string
  default     = "property_features"
}

variable "enable_vertex_endpoint_shell" {
  description = "When true, declare the encoder + reranker Vertex AI Endpoint shells. Default false in Phase 7 because serving runs on GKE + KServe; enable only when an empty endpoint scaffold is intentionally needed."
  type        = bool
  default     = false
}
