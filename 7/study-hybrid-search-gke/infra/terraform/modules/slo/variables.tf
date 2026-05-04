variable "project_id" {
  description = "GCP project ID hosting the SLO resources (must match the Cloud Run service's project)"
  type        = string
}

variable "region" {
  description = "Cloud Run region of the target service. Used to build the telemetry.resource_name URI for google_monitoring_custom_service."
  type        = string
}

variable "service_name" {
  description = "Target service name (Phase 5 search-api by default). For service_type=\"cloud_run\", this is the Cloud Run v2 service name; for service_type=\"k8s_service\", this is the GKE Service name (namespace is passed via k8s_namespace)."
  type        = string
  default     = "search-api"
}

variable "service_type" {
  description = "Which serving layer the SLOs attach to. \"cloud_run\" uses run.googleapis.com/* metrics + cloud_run_revision resource filter (Phase 5/6). \"k8s_service\" uses kubernetes.io/* metrics + k8s_container resource filter (Phase 7 GKE + KServe)."
  type        = string
  default     = "cloud_run"

  validation {
    condition     = contains(["cloud_run", "k8s_service"], var.service_type)
    error_message = "service_type must be one of: cloud_run, k8s_service."
  }
}

variable "k8s_namespace" {
  description = "Kubernetes namespace hosting the target Service. Only consulted when service_type=\"k8s_service\"."
  type        = string
  default     = "search"
}

variable "gke_cluster_name" {
  description = "GKE cluster name that hosts service_name. Only consulted when service_type=\"k8s_service\" to populate telemetry.resource_name (//container.googleapis.com/projects/<p>/locations/<r>/clusters/<c>)."
  type        = string
  default     = ""
}

variable "gke_cluster_location" {
  description = "GKE cluster location (region for Autopilot). Defaults to var.region when empty."
  type        = string
  default     = ""
}

variable "service_id_suffix" {
  description = "Suffix appended to google_monitoring_custom_service.service_id to avoid collision if the module is instantiated more than once (e.g. per-env)."
  type        = string
  default     = "slo"
}

variable "availability_goal" {
  description = "Request-based availability goal, 0 < goal < 1. Default 0.99 (99.0%) chosen as a learning-reasonable target; tighten only after burn-rate data warrants it."
  type        = number
  default     = 0.99

  validation {
    condition     = var.availability_goal > 0 && var.availability_goal < 1
    error_message = "availability_goal must be between 0 and 1 exclusive."
  }
}

variable "latency_threshold_ms" {
  description = "Latency threshold (milliseconds) for the latency SLO's distribution_cut range.max. Default 500ms matches the existing Phase 5 p95 alert."
  type        = number
  default     = 500
}

variable "latency_goal" {
  description = "Fraction of requests that must stay under latency_threshold_ms. Default 0.95 = p95 target."
  type        = number
  default     = 0.95

  validation {
    condition     = var.latency_goal > 0 && var.latency_goal < 1
    error_message = "latency_goal must be between 0 and 1 exclusive."
  }
}

variable "rolling_period_days" {
  description = "Rolling window for both SLOs. PMLE-typical choices are 7 or 30; 28 is another common pick to avoid month-boundary distortion. Keep 28 by default."
  type        = number
  default     = 28
}

variable "notification_channel_ids" {
  description = "List of google_monitoring_notification_channel resource IDs that receive SLO burn-rate alerts. Typically passed from module.monitoring.notification_channel_id wrapped in a list."
  type        = list(string)
}

variable "fast_burn_threshold" {
  description = "Fast-burn multiplier. Standard Google SRE workbook value is 14.4 (2% of 28-day error budget in 1h)."
  type        = number
  default     = 14.4
}

variable "slow_burn_threshold" {
  description = "Slow-burn multiplier. Standard value is 1.0 (10% of error budget in 1 day; GCP Monitoring filter は 24h 以下のみ受理するため 3d から短縮済)."
  type        = number
  default     = 1.0
}
