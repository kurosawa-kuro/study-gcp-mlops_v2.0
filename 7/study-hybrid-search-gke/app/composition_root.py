"""Composition root for the hybrid-search FastAPI app.

This module owns DI wiring. ``ContainerBuilder`` translates :class:`ApiSettings`
into a fully-constructed :class:`Container` of adapters and services. The
``Container`` is immutable; handlers (Phase A-2) consume it via FastAPI
``Depends``.

Phase A-1 status: factories were lifted out of ``app/main.py`` (was 699 lines;
factories occupied L67-328). ``app/main.py`` calls :meth:`ContainerBuilder.build`
during ``lifespan`` and stores the result on ``app.state.container``.

Adding a new component means: define a new ``_build_*`` helper here, add a
field to ``Container``, wire it in ``ContainerBuilder.build``. ``app/main.py``
should not grow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.container import InfraBuilder, MlBuilder, SearchBuilder
from app.observability import Observability
from app.services.data_catalog_service import DataCatalogService
from app.services.feedback_service import FeedbackService
from app.services.model_metrics_service import ModelMetricsService, default_cases_path
from app.services.protocols import (
    CandidateRetriever,
    DataCatalogReader,
    EncoderClient,
    FeedbackRecorder,
    LexicalSearchPort,
    PredictionPublisher,
    RankingLogPublisher,
    RerankerClient,
)
from app.services.protocols.feature_fetcher import FeatureFetcher
from app.services.protocols.popularity_scorer import PopularityScorer
from app.services.protocols.retrain_queries import RetrainQueries
from app.services.search_service import SearchService
from app.settings import ApiSettings


@dataclass(frozen=True)
class Container:
    """Immutable bag of fully-constructed adapters and services.

    All fields are populated once at app startup by
    :meth:`ContainerBuilder.build`. Handlers receive the container via
    FastAPI ``Depends`` (Phase A-2). Optional fields are ``None`` when the
    corresponding feature flag is disabled or required configuration is
    missing — handlers must check for ``None`` before use.

    Notes:
    - ``model_path`` mirrors ``reranker_client.model_path`` for endpoints
      that need to surface the active reranker model identifier without
      pulling the client.
    """

    settings: ApiSettings
    observability: Observability
    training_runs_table: str

    retrain_trigger_publisher: PredictionPublisher | None
    retrain_queries: RetrainQueries

    candidate_retriever: CandidateRetriever | None

    encoder_client: EncoderClient | None
    encoder_model_path: str | None

    reranker_client: RerankerClient | None
    model_path: str | None

    popularity_scorer: PopularityScorer | None

    ranking_log_publisher: RankingLogPublisher
    feedback_recorder: FeedbackRecorder

    # Phase 7 W2-8 で canonical 化済み: Vertex AI Feature Online Store fetcher。
    # FOS endpoint が unconfigured なら build 段で RuntimeError を出すため、
    # ``enable_search=True`` の Container では None になることはない。
    # ``enable_search=False`` (ENABLE_SEARCH=false での local boot contract)
    # の場合のみ None。
    feature_fetcher: FeatureFetcher | None

    # Services (Phase D-1) — constructed once at startup, depend only on
    # the adapter Ports above. Handlers receive these via FastAPI Depends.
    search_service: SearchService
    feedback_service: FeedbackService
    model_metrics_service: ModelMetricsService | None  # None if no SearchService wired
    data_catalog_service: DataCatalogService


class ContainerBuilder:
    """Builds a :class:`Container` from :class:`ApiSettings`.

    Splitting build into per-component ``_build_*`` helpers keeps each
    selection rule narrow (one feature flag → one adapter). The helpers are
    method-level rather than module-level functions so they share the
    ``self._settings`` reference without threading it through every call.
    """

    def __init__(
        self,
        settings: ApiSettings,
        *,
        observability: Observability | None = None,
    ) -> None:
        self._settings = settings
        # Observability is constructed once per app; the builder accepts an
        # external instance so ``app.main.create_app`` can register
        # ``/metrics`` before lifespan completes and still share the same
        # service_name / logger_factory with the Container.
        self._observability = observability or Observability.from_env()
        self._logger = self._observability.get_logger("app")
        self._bq_client: Any = None  # cached, see _bigquery()

    def _bigquery(self) -> Any:
        """Phase A-4 — single ``bigquery.Client`` shared across adapters.

        Multiple adapters (CandidateRetriever / SemanticSearch /
        PopularityScorer / RetrainQueries) previously each instantiated
        their own client. Centralising means one credentials round-trip,
        one connection pool, and one place to fail at startup if BigQuery
        is unreachable.

        Lazy + cached: the first caller pays the construction cost; later
        callers get the same instance. Returns ``None``-typed for unit
        tests that pass through fakes.
        """
        if self._bq_client is None:
            from google.cloud import bigquery

            self._bq_client = bigquery.Client(project=self._settings.project_id)
        return self._bq_client

    def build(self) -> Container:
        settings = self._settings
        infra = InfraBuilder(self).build()
        search_builder = SearchBuilder(self)
        search = search_builder.build()
        ml = MlBuilder(self).build()

        # Phase 7 PR-4 — Feature Online Store fetcher (default off).
        # ``resolve_feature_fetcher`` returns None when the backend selection
        # or FOS endpoint config is missing; SearchService treats None as
        # "no fresh-feature augmentation" and uses BQ-enriched values verbatim.
        feature_fetcher = (
            search_builder.resolve_feature_fetcher() if settings.enable_search else None
        )

        # Phase D-1 — service composition. Services are stateless wrappers
        # around the Ports above; constructed once at startup so handlers
        # don't pay per-request allocation cost.
        search_service = SearchService(
            retriever_default=search.candidate_retriever,
            encoder=search.encoder_client,
            publisher=infra.ranking_log_publisher,
            reranker=search.reranker_client,
            popularity_scorer=ml.popularity_scorer,
            feature_fetcher=feature_fetcher,
        )
        feedback_service = FeedbackService(recorder=infra.feedback_recorder)
        model_metrics_service = ModelMetricsService(
            search_service=search_service,
            default_cases_file=default_cases_path(),
        )
        data_catalog_service = DataCatalogService(reader=infra.data_catalog_reader)

        self._logger.info(
            "Startup complete; search_enabled=%s rerank_enabled=%s model_path=%s",
            settings.enable_search,
            search.reranker_client is not None,
            search.model_path,
        )

        return Container(
            settings=settings,
            observability=self._observability,
            training_runs_table=infra.training_runs_table,
            retrain_trigger_publisher=infra.retrain_trigger_publisher,
            retrain_queries=infra.retrain_queries,
            candidate_retriever=search.candidate_retriever,
            encoder_client=search.encoder_client,
            encoder_model_path=search.encoder_model_path,
            reranker_client=search.reranker_client,
            model_path=search.model_path,
            popularity_scorer=ml.popularity_scorer,
            ranking_log_publisher=infra.ranking_log_publisher,
            feedback_recorder=infra.feedback_recorder,
            feature_fetcher=feature_fetcher,
            search_service=search_service,
            feedback_service=feedback_service,
            model_metrics_service=model_metrics_service,
            data_catalog_service=data_catalog_service,
        )

    # ------------------------------------------------------------------ factories

    def _build_retrain_publisher(self) -> PredictionPublisher | None:
        return InfraBuilder(self).build_retrain_publisher()

    def _build_ranking_log_publisher(self) -> RankingLogPublisher:
        return InfraBuilder(self).build_ranking_log_publisher()

    def _build_feedback_recorder(self) -> FeedbackRecorder:
        return InfraBuilder(self).build_feedback_recorder()

    def _build_data_catalog_reader(self) -> DataCatalogReader:
        return InfraBuilder(self).build().data_catalog_reader

    def _build_candidate_retriever(
        self,
        *,
        override_lexical: LexicalSearchPort | None = None,
    ) -> CandidateRetriever:
        return SearchBuilder(self).build_candidate_retriever(override_lexical=override_lexical)

    def _build_encoder_client(self) -> tuple[EncoderClient | None, str | None]:
        return SearchBuilder(self).build_encoder_client()

    def _build_reranker_client(self) -> tuple[RerankerClient | None, str | None]:
        return SearchBuilder(self).build_reranker_client()

    def _build_popularity_scorer(self) -> PopularityScorer | None:
        return MlBuilder(self).build_popularity_scorer()
