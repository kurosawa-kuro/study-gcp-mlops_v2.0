variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Region for Cloud Scheduler (GKE クラスタと同一想定)"
  type        = string
}

variable "mlops_dataset_id" {
  description = "BQ dataset ID for mlops (training_runs, ranking_log, search_logs, feedback_events, validation_results)"
  type        = string
}

variable "ranking_log_table_id" {
  description = "BQ table ID for ranking_log (Pub/Sub subscription sink — one row per candidate)"
  type        = string
  default     = "ranking_log"
}

variable "feedback_events_table_id" {
  description = "BQ table ID for feedback_events (Pub/Sub subscription sink — user click/favorite/inquiry)"
  type        = string
  default     = "feedback_events"
}

variable "service_accounts" {
  description = "Map of SA resources emitted by the iam module. Uses .email for bindings."
  type        = any
}

variable "api_external_url" {
  description = "Public HTTPS URL of search-api (GKE Gateway hostname). Leave empty to skip Scheduler creation (bootstrap before cluster exists)."
  type        = string
  default     = ""
}
