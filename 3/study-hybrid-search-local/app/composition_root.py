"""Phase 3 — Composition root for the local hybrid-search FastAPI app.

Phase 7 の `app/container/` 分割 (`InfraBuilder` / `MlBuilder` / `SearchBuilder`)
を簡略化し、本ファイル 1 つで `Container` を組み立てる。Phase 3 の adapter は
すべて Local 完結 (Postgres + pgvector / Meilisearch / sentence-transformers /
LightGBM in-process) なので、ビルダー分割の必要性が薄い。

Phase 4 で adapter を Cloud Run / BigQuery / GCS / Pub/Sub に差し替える際、
本ファイルを Phase 7 と同じ container 分割パターンへ昇格させる想定。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.adapters.local_candidate_retriever import LocalCandidateRetriever
from app.services.adapters.local_e5_encoder import LocalE5Encoder
from app.services.adapters.local_lightgbm_reranker import LocalLightGBMReranker
from app.services.adapters.meilisearch_lexical_search import MeilisearchLexicalSearch
from app.services.adapters.pgvector_semantic_search import PgVectorSemanticSearch
from app.services.adapters.postgres_feature_fetcher import PostgresFeatureFetcher
from app.services.adapters.postgres_feedback_recorder import PostgresFeedbackRecorder
from app.services.adapters.postgres_ranking_log_publisher import PostgresRankingLogPublisher
from app.services.adapters.redis_synonym_expander import RedisSynonymExpander
from app.services.feedback_service import FeedbackService
from app.services.noop_adapters import NoopFeedbackRecorder, NoopRankingLogPublisher
from app.services.noop_adapters.noop_synonym_expander import NoopSynonymExpander
from app.services.protocols import (
    CandidateRetriever,
    EncoderClient,
    FeatureFetcher,
    FeedbackRecorder,
    LexicalSearchPort,
    RankingLogPublisher,
    RerankerClient,
    SemanticSearchPort,
    SynonymExpanderPort,
)
from app.services.search_service import SearchService
from app.settings import ApiSettings
from ml.common.logging import get_logger


@dataclass(frozen=True)
class Container:
    """Immutable bag of fully-constructed adapters and services.

    Phase 7 と同じ contract (handler は Depends(get_container) で受ける)。
    Phase 3 では BQML popularity / data_catalog / model_metrics / retrain は除外。
    """

    settings: ApiSettings

    # --- Port-level adapters ---
    lexical_search: LexicalSearchPort
    semantic_search: SemanticSearchPort
    candidate_retriever: CandidateRetriever
    encoder_client: EncoderClient | None
    reranker_client: RerankerClient | None
    feature_fetcher: FeatureFetcher | None
    ranking_log_publisher: RankingLogPublisher
    feedback_recorder: FeedbackRecorder
    synonym_expander: SynonymExpanderPort

    # Phase 4 以降で意味を持つ表示用 model_path (reranker_client.model_path mirror)
    model_path: str | None

    # --- Services (Phase D-1) ---
    search_service: SearchService
    feedback_service: FeedbackService


class ContainerBuilder:
    """Phase 3 ContainerBuilder。

    Phase 4 で同じ Port シグネチャに Cloud SDK adapter を差し替えるだけで動く構造を保つ。
    """

    def __init__(self, settings: ApiSettings) -> None:
        self._settings = settings
        self._logger = get_logger("app.composition_root")

    def build(self) -> Container:
        s = self._settings

        # --- Lexical (Meilisearch in Docker Compose) ---
        lexical: LexicalSearchPort
        if s.meili_base_url:
            lexical = MeilisearchLexicalSearch(
                base_url=s.meili_base_url,
                index_name=s.meili_index_name,
                master_key=s.meili_master_key,
            )
        else:
            from app.services.noop_adapters.noop_lexical_search import NoopLexicalSearch

            lexical = NoopLexicalSearch()

        # --- Semantic (pgvector cosine distance) ---
        semantic: SemanticSearchPort = PgVectorSemanticSearch(dsn=s.postgres_dsn)

        # --- Encoder (multilingual-e5 in-process) ---
        encoder_client: EncoderClient | None
        if s.enable_search:
            encoder_client = LocalE5Encoder(
                model_name=s.e5_model_name,
                max_seq_length=s.e5_max_seq_length,
            )
        else:
            encoder_client = None

        # --- Reranker (LightGBM in-process) ---
        # 学習済モデルが無い場合は None (fallback = lexical_rank だけで final_rank を決める)
        reranker_client: RerankerClient | None = None
        model_path: str | None = None
        latest_path = self._resolve_latest_model_path(s)
        if latest_path is not None:
            try:
                reranker_client = LocalLightGBMReranker(model_path=str(latest_path))
                model_path = str(latest_path)
                self._logger.info("Loaded reranker model from %s", latest_path)
            except Exception:
                self._logger.exception(
                    "Failed to load reranker model from %s; running in fallback mode",
                    latest_path,
                )

        # --- Feature fetcher (PostgreSQL feature_mart_property_features_daily) ---
        feature_fetcher: FeatureFetcher | None = (
            PostgresFeatureFetcher(dsn=s.postgres_dsn) if s.enable_search else None
        )

        # --- Candidate retriever = lexical + semantic + RRF を統合した Phase 3 専用 adapter ---
        candidate_retriever: CandidateRetriever = LocalCandidateRetriever(
            lexical_search=lexical,
            semantic_search=semantic,
            dsn=s.postgres_dsn,
            rrf_k=s.rrf_k,
            candidate_pool_size=s.candidate_pool_size,
        )

        # --- Publishers / Recorders (PostgreSQL) ---
        publisher: RankingLogPublisher
        feedback_recorder: FeedbackRecorder
        if s.postgres_dsn:
            publisher = PostgresRankingLogPublisher(dsn=s.postgres_dsn)
            feedback_recorder = PostgresFeedbackRecorder(dsn=s.postgres_dsn)
        else:
            publisher = NoopRankingLogPublisher()
            feedback_recorder = NoopFeedbackRecorder()

        # --- Synonym expander (Redis 同義語辞書, Phase 3 SYN-1) ---
        # ``synonym_backend == "redis"`` のとき RedisSynonymExpander を選択。
        # Redis の到達不能や package 未導入は警告のみで NoopSynonymExpander に
        # graceful degrade。/search の可用性は常に守る。
        synonym_expander: SynonymExpanderPort = NoopSynonymExpander()
        if s.synonym_backend == "redis" and s.redis_url:
            try:
                import redis
            except ImportError:
                self._logger.warning("redis package unavailable; synonym expansion disabled")
            else:
                client = redis.from_url(
                    s.redis_url,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0,
                    health_check_interval=30,
                )
                synonym_expander = RedisSynonymExpander(
                    client=client,
                    key_prefix=s.synonym_key_prefix,
                    max_synonyms_per_token=s.synonym_max_synonyms_per_token,
                )

        # --- Services ---
        search_service = SearchService(
            retriever_default=candidate_retriever,
            encoder=encoder_client,
            publisher=publisher,
            reranker=reranker_client,
            feature_fetcher=feature_fetcher,
            synonym_expander=synonym_expander,
        )
        feedback_service = FeedbackService(recorder=feedback_recorder)

        self._logger.info(
            "Phase 3 startup: enable_search=%s reranker=%s model_path=%s",
            s.enable_search,
            reranker_client is not None,
            model_path,
        )

        return Container(
            settings=s,
            lexical_search=lexical,
            semantic_search=semantic,
            candidate_retriever=candidate_retriever,
            encoder_client=encoder_client,
            reranker_client=reranker_client,
            feature_fetcher=feature_fetcher,
            ranking_log_publisher=publisher,
            feedback_recorder=feedback_recorder,
            synonym_expander=synonym_expander,
            model_path=model_path,
            search_service=search_service,
            feedback_service=feedback_service,
        )

    def _resolve_latest_model_path(self, s: ApiSettings) -> Path | None:
        """``ml/registry/artifacts/`` 配下から最新の model.lgb を探す。

        ``latest`` シンボリックリンク優先、なければ run_id ディレクトリ名で
        辞書順最大を選ぶ。見つからなければ None (fallback mode)。
        """
        root = Path(s.model_artifacts_root)
        if not root.is_absolute():
            root = Path(__file__).resolve().parents[1] / root
        if not root.exists():
            return None

        latest = root / "latest" / s.reranker_model_filename
        if latest.exists():
            return latest

        candidates = sorted(
            (p for p in root.iterdir() if p.is_dir() and p.name != "latest"),
            reverse=True,
        )
        for run_dir in candidates:
            model_file = run_dir / s.reranker_model_filename
            if model_file.exists():
                return model_file
        return None
