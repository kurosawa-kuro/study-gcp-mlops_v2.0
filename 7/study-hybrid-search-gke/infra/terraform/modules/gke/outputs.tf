output "cluster_name" {
  value = google_container_cluster.hybrid_search.name
}

output "cluster_location" {
  value = google_container_cluster.hybrid_search.location
}

output "cluster_endpoint" {
  value     = google_container_cluster.hybrid_search.endpoint
  sensitive = true
}

output "cluster_ca_certificate" {
  value     = google_container_cluster.hybrid_search.master_auth[0].cluster_ca_certificate
  sensitive = true
}

output "namespaces" {
  value = var.namespaces
}

output "ksa_names" {
  value = var.ksa_names
}
