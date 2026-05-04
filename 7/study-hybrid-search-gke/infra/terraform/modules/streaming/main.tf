# Phase 6 T2 — Dataflow streaming module.
#
# Provisions the Service Account (sa-dataflow) + IAM plumbing for a Flex
# Template streaming job that aggregates ranking-log events into hourly
# CTR rows. The actual template image + spec JSON is built out-of-band
# (scripts/setup/build_streaming_template.py) so Terraform does
# not block on Docker builds.
#
# The google_dataflow_flex_template_job resource is gated behind
# ``create_job`` since the job only launches cleanly once the template
# spec is in GCS; default false. Flip true after the template is built.

locals {
  sa_account_id   = "sa-dataflow"
  effective_sa    = var.service_account_email != "" ? var.service_account_email : try(google_service_account.dataflow[0].email, "")
  will_create_job = var.create_job && var.flex_template_gcs_path != "" && local.effective_sa != ""
}

resource "google_service_account" "dataflow" {
  count = var.create_service_account ? 1 : 0

  project      = var.project_id
  account_id   = local.sa_account_id
  display_name = "Dataflow streaming worker (Phase 6 T2)"
  description  = "Runs the ranking-log-hourly-ctr Flex Template streaming job. Pub/Sub subscriber + BQ data editor + Dataflow worker."
}

# Pub/Sub subscriber — required to pull from ranking-log.
resource "google_project_iam_member" "dataflow_pubsub_subscriber" {
  count = var.create_service_account ? 1 : 0

  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.dataflow[0].email}"
}

# Dataflow worker baseline + storage access.
resource "google_project_iam_member" "dataflow_worker" {
  count = var.create_service_account ? 1 : 0

  project = var.project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${google_service_account.dataflow[0].email}"
}

resource "google_project_iam_member" "dataflow_storage" {
  count = var.create_service_account ? 1 : 0

  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.dataflow[0].email}"
}

# BigQuery writer for the mlops dataset (hourly CTR sink).
resource "google_project_iam_member" "dataflow_bq_data_editor" {
  count = var.create_service_account ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.dataflow[0].email}"
}

resource "google_project_iam_member" "dataflow_bq_jobs" {
  count = var.create_service_account ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dataflow[0].email}"
}

resource "google_dataflow_flex_template_job" "ranking_log_hourly_ctr" {
  count = local.will_create_job ? 1 : 0

  provider = google-beta

  project                 = var.project_id
  region                  = var.region
  name                    = "ranking-log-hourly-ctr"
  container_spec_gcs_path = var.flex_template_gcs_path

  parameters = {
    input_topic           = var.ranking_log_topic_id
    output_table          = var.output_table_fqn
    window_size_sec       = "3600"
    temp_location         = var.temp_location
    staging_location      = var.staging_location
    service_account_email = local.effective_sa
  }

  on_delete = "cancel"

  lifecycle {
    # Dataflow streaming jobs are updated by launching a new job with
    # update_compatibility_version; Terraform should not recreate on every apply.
    ignore_changes = [parameters]
  }
}
