variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Region for meili-search Cloud Run service"
  type        = string
}

variable "service_accounts" {
  description = "Service account map from iam module"
  type        = any
}

variable "meili_data_bucket_name" {
  description = "GCS bucket name mounted to /meili_data by Cloud Storage FUSE"
  type        = string
  default     = "mlops-dev-a-meili-data"
}

variable "meili_image" {
  description = "Container image for meilisearch service. Default uses the official Meilisearch image from Docker Hub (Cloud Run supports public Docker Hub images)."
  type        = string
  default     = "docker.io/getmeili/meilisearch:v1.11"
}

variable "meili_master_key_secret_id" {
  description = "Secret Manager secret ID for the Meilisearch master key (e.g. 'meili-master-key'). Injected as MEILI_MASTER_KEY via --set-secrets."
  type        = string
  default     = "meili-master-key"
}
