# =========================================================================
# Vertex AI Vector Search — Phase 7 Wave 2 (W2-1).
#
# ME5 ベクトル検索の本番 serving index。embedding 生成履歴・メタデータの
# 正本は BigQuery 側 (`feature_mart.property_embeddings`) に置き続け、
# 本 module は serving 用 ANN index のみを provision する (data lake +
# serving index の二層構造、本 phase docs/01 §0 / §2)。
#
# Strangler 性質: Wave 1 PR-1 で adapter
# (`app/services/adapters/vertex_vector_search_semantic_search.py`) と
# `SEMANTIC_BACKEND` env 切替を先行実装済。本 module を apply して endpoint
# が provision された後、Wave 2 W2-7 (smoke) → W2-8 (default flip) で
# `SEMANTIC_BACKEND=vertex_vector_search` を本線に格上げする。
#
# 初回 backfill は `scripts/setup/backfill_vector_search_index.py` (W2-6)、
# 以降の incremental 更新は embed pipeline の VVS upsert step (Wave 1 PR-3)
# が `enable_vector_search_upsert=true` で daily run する想定。
# =========================================================================

resource "google_vertex_ai_index" "property_embeddings" {
  count    = var.enable_vector_search ? 1 : 0
  provider = google-beta

  region       = var.region
  display_name = var.index_display_name
  description  = "ME5 (multilingual-e5) embedding ANN serving index. Source-of-truth = BigQuery feature_mart.property_embeddings."

  metadata {
    contents_delta_uri = ""

    config {
      dimensions                  = var.dimensions
      approximate_neighbors_count = var.approximate_neighbors_count
      distance_measure_type       = var.distance_measure_type
      shard_size                  = var.shard_size
      # COSINE_DISTANCE distanceMeasureType requires UNIT_L2_NORM featureNormType
      # (GCP Vertex AI Vector Search 制約)。`NONE` だと API が
      # ``Error 400: Index with COSINE_DISTANCE distanceMeasureType currently only
      # supports UNIT_L2_NORM featureNormType`` を返して create に失敗する。
      # multilingual-e5 の embedding は L2 normalize 前提で training されている
      # (HuggingFace モデルカード) ため UNIT_L2_NORM が canonical。
      feature_norm_type           = "UNIT_L2_NORM"

      algorithm_config {
        tree_ah_config {
          leaf_node_embedding_count    = var.leaf_node_embedding_count
          leaf_nodes_to_search_percent = var.leaf_nodes_to_search_percent
        }
      }
    }
  }

  index_update_method = "STREAM_UPDATE"

  labels = var.labels

  # 永続化契約 (2026-05-03、`docs/tasks/TASKS_ROADMAP.md §4.9`): Index は
  # `destroy-all` で **state rm + GCP 残置** する (Terraform 依存閉包で
  # `lifecycle.prevent_destroy = true` だけでは依存元 resource の destroy が
  # 連鎖して `Instance cannot be destroyed` で全体 destroy が止まる事故を
  # 2026-05-03 に観測したため、prevent_destroy は採用しない)。永続化は
  # `scripts/setup/destroy_all.py::PERSISTENT_VVS_RESOURCES` の state rm
  # と、次回 `deploy-all` の `terraform import` で復元する設計。
}

resource "google_vertex_ai_index_endpoint" "property_embeddings" {
  count    = var.enable_vector_search ? 1 : 0
  provider = google-beta

  region       = var.region
  display_name = var.index_endpoint_display_name
  description  = "Endpoint that exposes property_embeddings index for search-api / KServe encoder via find_neighbors."

  public_endpoint_enabled = true

  labels = var.labels

  # 永続化契約 (2026-05-03): Index Endpoint も Index と同じく `destroy-all`
  # で **state rm + GCP 残置** する。`prevent_destroy` は依存閉包で全 destroy
  # を止めるリスクがあるため不採用。詳細は `google_vertex_ai_index` 側コメント。
}

resource "google_vertex_ai_index_endpoint_deployed_index" "property_embeddings" {
  count    = var.enable_vector_search ? 1 : 0
  provider = google-beta

  index_endpoint    = google_vertex_ai_index_endpoint.property_embeddings[0].id
  deployed_index_id = var.deployed_index_id
  display_name      = var.deployed_index_id
  index             = google_vertex_ai_index.property_embeddings[0].id

  automatic_resources {
    min_replica_count = var.min_replica_count
    max_replica_count = var.max_replica_count
  }

  dynamic "deployed_index_auth_config" {
    for_each = []
    content {}
  }

  depends_on = [
    google_vertex_ai_index.property_embeddings,
    google_vertex_ai_index_endpoint.property_embeddings,
  ]
}
