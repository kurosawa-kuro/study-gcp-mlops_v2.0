output "dag_bucket" {
  description = "GCS prefix Composer reads DAGs from (e.g. `gs://<region>-<env>-<hash>-bucket/dags`). Consumed by `scripts/deploy/composer_deploy_dags.py` via `terraform output -json`."
  value       = var.enable_composer ? google_composer_environment.this[0].config[0].dag_gcs_prefix : ""
}

output "airflow_uri" {
  description = "Airflow UI URL of the Composer environment. Used by `make ops-composer-list-runs` smoke."
  value       = var.enable_composer ? google_composer_environment.this[0].config[0].airflow_uri : ""
}

output "environment_name" {
  description = "Composer environment name (used by `gcloud composer environments run --environment=<name>`)."
  value       = var.environment_name
}

output "enabled" {
  description = "Whether the Composer environment is provisioned (mirrors `var.enable_composer`)."
  value       = var.enable_composer
}
