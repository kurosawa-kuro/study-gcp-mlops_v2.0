variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Region for regional resources (Artifact Registry, Secret Manager replication)"
  type        = string
}

variable "artifact_repo_id" {
  description = "Artifact Registry repository ID to create for container images"
  type        = string
}

variable "models_bucket_name" {
  description = "GCS bucket name for trained model artifacts (immutable under lgbm/{date}/{run_id}/)"
  type        = string
}

variable "pipeline_root_bucket_name" {
  description = "GCS bucket name for Vertex AI pipeline root and compiled pipeline templates"
  type        = string
}

variable "artifacts_bucket_name" {
  description = "GCS bucket name for general-purpose artifacts (code drops, Dataform logs)"
  type        = string
}

variable "service_accounts" {
  description = "Map of SA resources emitted by the iam module. Uses .email for IAM bindings."
  type        = any
}

variable "github_repo" {
  description = "GitHub repository (owner/name) used for Dataform git_remote_settings. Empty string = local-only Dataform repo."
  type        = string
  default     = ""
}

variable "dataform_repository_id" {
  description = "Dataform repository name (must match REPOSITORY env in .github/workflows/deploy-dataform.yml)"
  type        = string
  default     = "hybrid-search-cloud"
}

variable "dataform_git_token_secret_version" {
  description = "Secret Manager resource ID (projects/.../secrets/dataform-github-token/versions/latest) for the GitHub PAT that Dataform uses to pull definitions/. Empty string = no remote sync, use Dataform UI."
  type        = string
  default     = ""
}

variable "github_deployer_sa_email" {
  description = "Email of sa-github-deployer; granted Dataform editor to allow CI-triggered compilationResults. Empty string = skip binding."
  type        = string
  default     = ""
}

variable "enable_deletion_protection" {
  description = "Toggle BQ table deletion_protection across the data module. Default true (production-safe). `make destroy-all` flips this to false in a preceding apply so the subsequent terraform destroy can proceed (Terraform refuses to destroy a table whose state still says deletion_protection=true, even if the actual GCP resource was unprotected via bq CLI)."
  type        = bool
  default     = true
}
