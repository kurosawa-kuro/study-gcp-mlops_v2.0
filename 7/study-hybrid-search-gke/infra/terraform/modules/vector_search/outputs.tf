output "index" {
  description = "Vertex AI Vector Search index resource (null when disabled)"
  value = (
    length(google_vertex_ai_index.property_embeddings) > 0
    ? google_vertex_ai_index.property_embeddings[0]
    : null
  )
}

output "index_endpoint" {
  description = "Vertex AI Vector Search index endpoint resource (null when disabled)"
  value = (
    length(google_vertex_ai_index_endpoint.property_embeddings) > 0
    ? google_vertex_ai_index_endpoint.property_embeddings[0]
    : null
  )
}

output "index_endpoint_id" {
  description = "Numeric / fully-qualified resource name of the index endpoint, consumed via VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT_ID env. Empty string when disabled so the search-api adapter stays in no-op mode."
  value = (
    length(google_vertex_ai_index_endpoint.property_embeddings) > 0
    ? google_vertex_ai_index_endpoint.property_embeddings[0].name
    : ""
  )
}

output "deployed_index_id" {
  description = "Deployed index ID consumed via VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID env. Empty string when disabled."
  value = (
    length(google_vertex_ai_index_endpoint_deployed_index.property_embeddings) > 0
    ? google_vertex_ai_index_endpoint_deployed_index.property_embeddings[0].deployed_index_id
    : ""
  )
}

output "index_resource_name" {
  description = "Vertex AI Vector Search index resource name (full path) consumed by the embed pipeline VVS upsert step (`vector_search_index_resource_name` KFP param). Empty string when disabled so the upsert component stays no-op."
  value = (
    length(google_vertex_ai_index.property_embeddings) > 0
    ? google_vertex_ai_index.property_embeddings[0].name
    : ""
  )
}
