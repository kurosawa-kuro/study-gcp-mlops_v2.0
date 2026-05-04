variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository (owner/name) trusted by Workload Identity Federation"
  type        = string
}

variable "admin_user_emails" {
  description = "Developer user account emails that need to impersonate sa-api for local one-off ops (e.g. Meilisearch document sync that requires OIDC token with audience=meili-search URL). Empty list disables the binding."
  type        = list(string)
  default     = []
}
