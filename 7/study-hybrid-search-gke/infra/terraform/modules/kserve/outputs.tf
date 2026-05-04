output "search_namespace" {
  value = kubernetes_namespace.search.metadata[0].name
}

output "inference_namespace" {
  value = kubernetes_namespace.inference.metadata[0].name
}

output "api_ksa" {
  value = {
    name      = kubernetes_service_account.api.metadata[0].name
    namespace = kubernetes_service_account.api.metadata[0].namespace
  }
}

output "encoder_ksa" {
  value = {
    name      = kubernetes_service_account.encoder.metadata[0].name
    namespace = kubernetes_service_account.encoder.metadata[0].namespace
  }
}

output "reranker_ksa" {
  value = {
    name      = kubernetes_service_account.reranker.metadata[0].name
    namespace = kubernetes_service_account.reranker.metadata[0].namespace
  }
}
