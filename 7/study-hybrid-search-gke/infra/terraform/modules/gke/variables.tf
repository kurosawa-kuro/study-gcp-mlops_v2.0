variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Region for the GKE cluster (Autopilot is regional)"
  type        = string
}

variable "cluster_name" {
  description = "GKE Autopilot cluster name"
  type        = string
  default     = "hybrid-search"
}

variable "deletion_protection" {
  description = "Cluster deletion protection. Set to false in dev to allow destroy-all"
  type        = bool
  default     = false
}

variable "release_channel" {
  description = "GKE release channel (RAPID / REGULAR / STABLE)"
  type        = string
  default     = "REGULAR"
}

variable "service_accounts" {
  description = "Map of SA resources emitted by the iam module. Uses .email / .name for Workload Identity bindings."
  type        = any
}

variable "namespaces" {
  description = "Kubernetes namespaces that will host Workload-Identity-bound KSAs"
  type = object({
    search           = string
    inference        = string
    external_secrets = string
  })
  default = {
    search           = "search"
    inference        = "kserve-inference"
    external_secrets = "external-secrets"
  }
}

variable "ksa_names" {
  description = "Kubernetes ServiceAccount names per workload (bound to GCP SAs via Workload Identity)"
  type = object({
    api              = string
    encoder          = string
    reranker         = string
    external_secrets = string
  })
  default = {
    api              = "search-api"
    encoder          = "encoder"
    reranker         = "reranker"
    external_secrets = "external-secrets"
  }
}
