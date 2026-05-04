output "service_account_email" {
  description = "Email of sa-dataflow (or the caller-supplied override)."
  value       = local.effective_sa
}

output "job_id" {
  description = "google_dataflow_flex_template_job.id — empty when create_job=false."
  value       = local.will_create_job ? google_dataflow_flex_template_job.ranking_log_hourly_ctr[0].id : ""
}

output "job_name" {
  description = "Dataflow job name — empty when create_job=false."
  value       = local.will_create_job ? google_dataflow_flex_template_job.ranking_log_hourly_ctr[0].name : ""
}
