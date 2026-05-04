output "service_accounts" {
  description = "Map of runtime SA resources (use .email / .name / .id from caller)"
  value = {
    api               = google_service_account.api
    job_train         = google_service_account.job_train
    job_embed         = google_service_account.job_embed
    dataform          = google_service_account.dataform
    scheduler         = google_service_account.scheduler
    pipeline          = google_service_account.pipeline
    endpoint_encoder  = google_service_account.endpoint_encoder
    endpoint_reranker = google_service_account.endpoint_reranker
    pipeline_trigger  = google_service_account.pipeline_trigger
    external_secrets  = google_service_account.external_secrets
    composer          = google_service_account.composer
  }
}

output "github_deployer_sa_email" {
  description = "sa-github-deployer email — register as GitHub Actions var DEPLOYER_SERVICE_ACCOUNT"
  value       = google_service_account.github_deployer.email
}

output "workload_identity_provider" {
  description = "WIF provider resource name — register as GitHub Actions var WORKLOAD_IDENTITY_PROVIDER"
  value       = google_iam_workload_identity_pool_provider.github.name
}
