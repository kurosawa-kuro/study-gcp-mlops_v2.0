variable "project_id" {
  description = "GCP project hosting the Dataflow Flex Template + streaming job."
  type        = string
}

variable "region" {
  description = "Region for Dataflow job + temp/staging buckets. Must match the Pub/Sub topic region."
  type        = string
}

variable "ranking_log_topic_id" {
  description = "Fully-qualified Pub/Sub topic resource ID for ranking-log (projects/.../topics/ranking-log). The streaming job reads from this."
  type        = string
}

variable "output_table_fqn" {
  description = "BigQuery output table in ``project:dataset.table`` form — typically ``mlops-dev-a:mlops.ranking_log_hourly_ctr``."
  type        = string
}

variable "flex_template_gcs_path" {
  description = "GCS path of the compiled Flex Template spec JSON (e.g. gs://mlops-dev-a-artifacts/dataflow/ranking-log-hourly-ctr.json). Built by scripts/setup/build_streaming_template.py — module creates the SA but does not build the template."
  type        = string
  default     = ""
}

variable "temp_location" {
  description = "GCS temp path used by Dataflow workers."
  type        = string
}

variable "staging_location" {
  description = "GCS staging path for Dataflow worker binaries."
  type        = string
}

variable "create_job" {
  description = "Create google_dataflow_flex_template_job. Set false when only the SA + IAM scaffolding is needed (template not yet built)."
  type        = bool
  default     = false
}

variable "service_account_email" {
  description = "SA email used by the Dataflow job. Created in this module as sa-dataflow; callers can override to share an existing SA."
  type        = string
  default     = ""
}

variable "create_service_account" {
  description = "Create a dedicated sa-dataflow service account inside this module. Set false when service_account_email points to an existing SA owned elsewhere."
  type        = bool
  default     = true
}
