"""API settings."""

from __future__ import annotations

from functools import cached_property

from pydantic import BaseModel, SecretStr

from ml.common.config import BaseAppSettings


class FeatureFlags(BaseModel):
    enable_search: bool
    enable_rerank: bool


class MessagingSettings(BaseModel):
    ranking_log_topic: str
    feedback_topic: str
    retrain_topic: str


class KServeSettings(BaseModel):
    encoder_url: str
    reranker_url: str
    reranker_explain_url: str
    predict_timeout_seconds: float


class PopularitySettings(BaseModel):
    enabled: bool
    model_fqn: str


class SynonymSettings(BaseModel):
    backend: str  # "redis" | "none"
    redis_url: str
    redis_password_env: str
    key_prefix: str
    max_synonyms_per_token: int


class ApiSettings(BaseAppSettings):
    # --- /search + /feedback -------------------------------------------------
    enable_search: bool = False
    ranking_log_topic: str = "ranking-log"
    feedback_topic: str = "search-feedback"
    retrain_topic: str = "retrain-trigger"
    bq_table_property_embeddings: str = "property_embeddings"
    bq_table_property_features_daily: str = "property_features_daily"
    bq_table_properties_cleaned: str = "properties_cleaned"
    meili_base_url: str = ""
    meili_service: str = "meili-search"
    meili_index_name: str = "properties"
    meili_api_key: str = ""
    meili_master_key: SecretStr = SecretStr("")  # Secret Manager: meili-master-key
    meili_require_identity_token: bool = True
    meili_impersonate_service_account: str = ""
    meili_token_audience: str = ""

    # --- Vertex AI location (used by Model Registry / Pipelines) -------------
    vertex_location: str = "asia-northeast1"

    # --- Vertex AI Vector Search (Phase 7 canonical semantic lane) ----------
    # W2-8 で BQ semantic search backend は撤去。`/search` の semantic lane は
    # 常に Vertex Vector Search の find_neighbors を使う。Resource ID は
    # `make deploy-all` の `configmap_overlay` step が Terraform output から
    # search-api ConfigMap へ注入する。空のまま起動すると Container build 時に
    # `RuntimeError` で fail-loud (silent fallback はしない)。
    vertex_vector_search_index_endpoint_id: str = ""
    vertex_vector_search_deployed_index_id: str = ""

    # --- Vertex AI Feature Online Store (Phase 7 canonical feature fetch) ---
    # W2-8 で BQ feature fetcher は撤去。reranker 入力の fresh feature 取得は
    # 常に Feature View 経由。空のまま起動すると Container build 時に
    # `RuntimeError` で fail-loud。
    vertex_feature_online_store_id: str = ""
    vertex_feature_view_id: str = ""
    vertex_feature_online_store_endpoint: str = ""

    # --- KServe inference endpoints (cluster-local HTTP) ----------------------
    kserve_encoder_url: str = ""
    kserve_reranker_url: str = ""
    kserve_reranker_explain_url: str = ""
    kserve_predict_timeout_seconds: float = 30.0

    # --- Phase 6 /search rerank (optional bolt-on) ---------------------------
    enable_rerank: bool = False

    # --- Phase 6 T1 — BQML popularity scorer --------------------------------
    bqml_popularity_enabled: bool = False
    bqml_popularity_model_fqn: str = ""

    # --- Phase 7 SYN-1 — Redis synonym dictionary (lexical query expansion) -
    # Architecture (`docs/architecture/01_仕様と設計.md` §2.2.1) places
    # Redis as the synonym dictionary feeding Meilisearch BM25. Default
    # ``synonym_backend="none"`` preserves Phase 5 / 6 behaviour; flip to
    # ``"redis"`` and supply ``synonym_redis_url`` (Cloud Memorystore URI)
    # via ConfigMap to enable lexical query expansion.
    synonym_backend: str = "none"
    synonym_redis_url: str = ""
    synonym_redis_password_env: str = "REDIS_AUTH"
    synonym_key_prefix: str = "syn:"
    synonym_max_synonyms_per_token: int = 8

    @cached_property
    def feature_flags(self) -> FeatureFlags:
        return FeatureFlags(
            enable_search=self.enable_search,
            enable_rerank=self.enable_rerank,
        )

    @cached_property
    def messaging(self) -> MessagingSettings:
        return MessagingSettings(
            ranking_log_topic=self.ranking_log_topic,
            feedback_topic=self.feedback_topic,
            retrain_topic=self.retrain_topic,
        )

    @cached_property
    def kserve(self) -> KServeSettings:
        return KServeSettings(
            encoder_url=self.kserve_encoder_url,
            reranker_url=self.kserve_reranker_url,
            reranker_explain_url=self.kserve_reranker_explain_url,
            predict_timeout_seconds=self.kserve_predict_timeout_seconds,
        )

    @cached_property
    def popularity(self) -> PopularitySettings:
        return PopularitySettings(
            enabled=self.bqml_popularity_enabled,
            model_fqn=self.bqml_popularity_model_fqn,
        )

    @cached_property
    def synonym(self) -> SynonymSettings:
        return SynonymSettings(
            backend=self.synonym_backend,
            redis_url=self.synonym_redis_url,
            redis_password_env=self.synonym_redis_password_env,
            key_prefix=self.synonym_key_prefix,
            max_synonyms_per_token=self.synonym_max_synonyms_per_token,
        )
