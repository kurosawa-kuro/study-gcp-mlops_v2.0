output "host" {
  description = "Memorystore primary host (use as redis://HOST:PORT/0)"
  value       = google_redis_instance.synonym.host
}

output "port" {
  description = "Memorystore primary port"
  value       = google_redis_instance.synonym.port
}

output "redis_url" {
  description = "Composed redis:// URL for ``synonym_redis_url`` settings (sans AUTH)"
  value       = "redis://${google_redis_instance.synonym.host}:${google_redis_instance.synonym.port}/0"
}

output "auth_secret_id" {
  description = "Secret Manager secret holding the AUTH string (or empty when AUTH is disabled)"
  value       = var.auth_enabled ? google_secret_manager_secret.redis_auth[0].secret_id : ""
}

output "instance_name" {
  description = "Memorystore instance name (for ops scripts)"
  value       = google_redis_instance.synonym.name
}
