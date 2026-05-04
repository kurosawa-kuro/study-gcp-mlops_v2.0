output "meili_service" {
  description = "Cloud Run meili-search service resource"
  value       = google_cloud_run_v2_service.meili_search
}

output "meili_base_url" {
  description = "HTTPS base URL used by search-api to call meili-search"
  value       = google_cloud_run_v2_service.meili_search.uri
}

output "meili_data_bucket" {
  description = "GCS bucket mounted to /meili_data"
  value       = google_storage_bucket.meili_data
}
