variable "project_id" {
  description = "GCP project hosting the Vertex AI Vector Search resources"
  type        = string
}

variable "region" {
  description = "Region for Vertex AI Vector Search index / endpoint"
  type        = string
}

variable "enable_vector_search" {
  description = "When true, provision the Vertex AI Vector Search index + endpoint + deployed index. Default false because the index incurs ongoing per-replica cost; flip on after the embedding source (BigQuery `feature_mart.property_embeddings`) and the backfill script are ready."
  type        = bool
  default     = false
}

variable "index_display_name" {
  description = "Vertex AI Vector Search index display name. Phase 7 canonical = `property-embeddings` (matches embed pipeline output)."
  type        = string
  default     = "property-embeddings"
}

variable "index_endpoint_display_name" {
  description = "Vertex AI Vector Search index endpoint display name."
  type        = string
  default     = "property-embeddings-endpoint"
}

variable "deployed_index_id" {
  description = "Deployed index ID exposed by the index endpoint. Must be unique within the endpoint and stable across applies (consumed via `VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID` env). Bumped v1→v2 on 2026-05-02 then v2→v3 on 2026-05-03: GCP API holds the previous deployed_index_id in 'being undeployed / failed' soft-state for an extended grace period (>30 min observed) even after `gcloud ai index-endpoints list` reports it as gone, blocking re-creation with HTTP 400 'There exists a DeployedIndex with same ID either in failed state or being undeployed'. Bumping the version sidesteps the grace period; destroy-all's `undeploy_all_vvs_deployed_indexes` guard prevents stale state for future clean PDCA cycles."
  type        = string
  default     = "property_embeddings_v3"
}

variable "dimensions" {
  description = "Embedding vector dimensionality. Must match `ml/serving/encoder.py::E5_VECTOR_DIM` and `app/services/adapters/internal/kserve_common.py::EXPECTED_EMBEDDING_DIM`."
  type        = number
  default     = 768
}

variable "distance_measure_type" {
  description = "Distance metric. ME5 vectors are L2-normalized; COSINE_DISTANCE is the canonical choice."
  type        = string
  default     = "COSINE_DISTANCE"
}

variable "approximate_neighbors_count" {
  description = "Default approximate_neighbors_count for ANN tree-AH. The search-api adapter sets the runtime `num_neighbors` separately."
  type        = number
  default     = 150
}

variable "shard_size" {
  description = "Vertex Vector Search shard size. SHARD_SIZE_SMALL is enough for the learning repo's ~10K embeddings."
  type        = string
  default     = "SHARD_SIZE_SMALL"
}

variable "leaf_node_embedding_count" {
  description = "Tree-AH leaf node embedding count. Smaller = faster build, less recall."
  type        = number
  default     = 1000
}

variable "leaf_nodes_to_search_percent" {
  description = "Tree-AH leaf nodes scanned per query (percent). Higher = better recall, more latency."
  type        = number
  default     = 10
}

variable "min_replica_count" {
  description = "Deployed index minimum replica count. Set to 1 for the learning repo (PDCA cost minimization). Production typically uses 2+."
  type        = number
  default     = 1
}

variable "max_replica_count" {
  description = "Deployed index maximum replica count. Autoscaling cap for the index endpoint."
  type        = number
  default     = 1
}

variable "service_account_email" {
  description = "Service account that the deployed index runs as (= sa-api or sa-pipeline, both need aiplatform.user). Pass `null` to let Vertex use the default Compute Engine SA."
  type        = string
  default     = null
}

variable "labels" {
  description = "Resource labels propagated to index / endpoint / deployed index"
  type        = map(string)
  default     = {}
}
