# =========================================================================
# Cloud Memorystore for Redis — synonym dictionary backing the
# `SynonymExpanderPort` (Phase 7 SYN-1). Architecture:
# `docs/architecture/01_仕様と設計.md` §2.2.1 places ``Syn[Redis 同義語辞書]``
# in the lexical lane between the API and Meilisearch BM25.
#
# Capacity sizing rationale: ~10⁴ canonical terms × ~10 synonyms each ≈
# a few MiB on disk. The 1 GiB BASIC tier instance is far above the
# working set; the slot is sized for headroom + free-tier eligibility,
# not for vertical scaling. STANDARD_HA is recommended for prod.
# =========================================================================

resource "google_redis_instance" "synonym" {
  project        = var.project_id
  name           = var.instance_name
  region         = var.region
  tier           = var.tier
  memory_size_gb = var.memory_size_gb
  redis_version  = var.redis_version

  authorized_network = var.vpc_network
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  auth_enabled       = var.auth_enabled

  redis_configs = {
    # SYN-1 — synonym dict is read-mostly; LRU keeps memory bounded if
    # background batch loaders ever exceed the configured capacity.
    maxmemory-policy = "allkeys-lru"
  }

  display_name = "Phase 7 synonym dictionary (lexical query expansion)"
  labels = {
    phase = "7"
    role  = "synonym-dict"
  }
}

# AUTH string mirrored into Secret Manager so the search-api KSA can pull
# it via External Secrets Operator (same pattern as ``meili-master-key``).
resource "google_secret_manager_secret" "redis_auth" {
  count     = var.auth_enabled ? 1 : 0
  project   = var.project_id
  secret_id = var.auth_secret_id

  replication {
    auto {}
  }

  labels = {
    phase = "7"
    role  = "synonym-redis-auth"
  }
}

resource "google_secret_manager_secret_version" "redis_auth" {
  count       = var.auth_enabled ? 1 : 0
  secret      = google_secret_manager_secret.redis_auth[0].id
  secret_data = google_redis_instance.synonym.auth_string
}
