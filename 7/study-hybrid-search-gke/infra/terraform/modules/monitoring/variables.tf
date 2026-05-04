variable "project_id" {
  description = "GCP project ID hosting alert policies + the Scheduled Query"
  type        = string
}

variable "region" {
  description = "BQ dataset region. Required by google_bigquery_data_transfer_config (default jurisdiction US fails against an asia-northeast1 dataset)."
  type        = string
}

variable "mlops_dataset_id" {
  description = "BQ dataset ID where validation_results table lives"
  type        = string
}

variable "ranker_skew_sql_path" {
  description = "Absolute path to infra/sql/monitoring/validate_feature_skew.sql (ranker-side skew check)"
  type        = string
}

variable "model_output_drift_sql_path" {
  description = "Absolute path to infra/sql/monitoring/validate_model_output_drift.sql (self-managed KServe drift substitute)"
  type        = string
}

variable "service_accounts" {
  description = "Map of SA resources emitted by the iam module. The dataform SA is used as google_bigquery_data_transfer_config.service_account_name so the Scheduled Query has a valid credential (otherwise DTS creation fails with 'Failed to find a valid credential')."
  type        = any
}

variable "oncall_email" {
  description = "Email to notify on alerts. Required — no default (prior placeholder oncall@example.com was a footgun)."
  type        = string

  validation {
    condition     = length(var.oncall_email) > 0 && can(regex("@", var.oncall_email))
    error_message = "oncall_email must be a non-empty address containing '@'. Pass via -var or tfvars (see docs/runbook/05_運用.md STEP 11)."
  }
}
