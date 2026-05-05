variable "project_id" {
  type        = string
  description = "GCP project that owns the Memorystore instance"
}

variable "region" {
  type        = string
  description = "Region (e.g. asia-northeast1) — must match GKE region"
}

variable "instance_name" {
  type        = string
  description = "Cloud Memorystore for Redis instance ID"
  default     = "phase7-synonym"
}

variable "tier" {
  type        = string
  description = "BASIC | STANDARD_HA — Standard tier ships replica + automatic failover"
  default     = "BASIC"
}

variable "memory_size_gb" {
  type        = number
  description = "Capacity in GiB. The synonym dictionary fits comfortably in 1 GiB"
  default     = 1
}

variable "redis_version" {
  type        = string
  description = "Redis engine version"
  default     = "REDIS_7_2"
}

variable "auth_enabled" {
  type        = bool
  description = "Enable AUTH (random secret managed by Memorystore)"
  default     = true
}

variable "vpc_network" {
  type        = string
  description = "VPC self-link the GKE cluster runs in (Memorystore peers to it)"
}

variable "auth_secret_id" {
  type        = string
  description = "Secret Manager secret ID where the AUTH string is mirrored for KSA / ESO"
  default     = "phase7-synonym-redis-auth"
}
