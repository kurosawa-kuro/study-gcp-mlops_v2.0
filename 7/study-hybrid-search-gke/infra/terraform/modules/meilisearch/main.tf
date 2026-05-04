resource "google_storage_bucket" "meili_data" {
  name                        = var.meili_data_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
}

resource "google_service_account" "meili" {
  account_id   = "sa-meili"
  display_name = "Cloud Run Service (Meilisearch) runtime SA"
}

resource "google_storage_bucket_iam_member" "meili_bucket_admin" {
  bucket = google_storage_bucket.meili_data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.meili.email}"
}

resource "google_cloud_run_v2_service" "meili_search" {
  name     = "meili-search"
  location = var.region

  template {
    service_account       = google_service_account.meili.email
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    scaling {
      min_instance_count = 1
      max_instance_count = 2
    }

    volumes {
      name = "meili-data"
      gcs {
        bucket    = google_storage_bucket.meili_data.name
        read_only = false
      }
    }

    containers {
      image = var.meili_image
      # Meilisearch 公式 image の default port は 7700、Cloud Run は 8080 を
      # listen 要求。env `MEILI_HTTP_ADDR=0.0.0.0:8080` + `ports.container_port=8080`
      # で整合させる (2026-04-23 Phase 5 実運用で確定)。
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
      }

      env {
        name  = "MEILI_DB_PATH"
        value = "/meili_data"
      }

      env {
        name  = "MEILI_HTTP_ADDR"
        value = "0.0.0.0:8080"
      }

      env {
        name = "MEILI_MASTER_KEY"
        value_source {
          secret_key_ref {
            secret  = var.meili_master_key_secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "meili-data"
        mount_path = "/meili_data"
      }
    }
  }

  ingress = "INGRESS_TRAFFIC_ALL"

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "api_invoker" {
  name     = google_cloud_run_v2_service.meili_search.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_accounts.api.email}"
}

# Secret Accessor: meili SA が Cloud Run 起動時に MEILI_MASTER_KEY を読み込めるよう
# secretmanager.secretAccessor を付与する。
resource "google_secret_manager_secret_iam_member" "meili_sa_master_key_access" {
  secret_id = var.meili_master_key_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.meili.email}"
}
