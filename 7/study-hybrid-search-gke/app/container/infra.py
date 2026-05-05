"""Infrastructure-facing dependency assembly.

This module owns Pub/Sub and query-side support objects that are shared
across API services.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from app.services.adapters import (
    BigQueryDataCatalogReader,
    BigQueryRetrainQueries,
    PubSubFeedbackRecorder,
    PubSubPublisher,
    PubSubRankingLogPublisher,
)
from app.services.adapters.redis_synonym_expander import RedisSynonymExpander
from app.services.noop_adapters import (
    NoopDataCatalogReader,
    NoopFeedbackRecorder,
    NoopRankingLogPublisher,
    NoopRetrainQueries,
)
from app.services.noop_adapters.noop_synonym_expander import NoopSynonymExpander
from app.services.protocols import (
    DataCatalogReader,
    FeedbackRecorder,
    PredictionPublisher,
    RankingLogPublisher,
    SynonymExpanderPort,
)
from app.services.protocols.retrain_queries import RetrainQueries
from app.settings import ApiSettings
from ml.common.logging import get_logger

logger = get_logger("app.container.infra")


class InfraBuilderContext(Protocol):
    _settings: ApiSettings

    def _bigquery(self) -> Any: ...


@dataclass(frozen=True)
class InfraComponents:
    retrain_trigger_publisher: PredictionPublisher | None
    retrain_queries: RetrainQueries
    data_catalog_reader: DataCatalogReader
    ranking_log_publisher: RankingLogPublisher
    feedback_recorder: FeedbackRecorder
    training_runs_table: str
    synonym_expander: SynonymExpanderPort


class InfraBuilder:
    def __init__(self, context: InfraBuilderContext) -> None:
        self._context = context

    @property
    def _settings(self) -> ApiSettings:
        return self._context._settings

    def build(self) -> InfraComponents:
        settings = self._settings
        training_runs_table = (
            f"{settings.project_id}.{settings.bq_dataset_mlops}.{settings.bq_table_training_runs}"
        )
        if not settings.enable_search:
            return InfraComponents(
                retrain_trigger_publisher=None,
                retrain_queries=NoopRetrainQueries(),
                data_catalog_reader=NoopDataCatalogReader(),
                ranking_log_publisher=NoopRankingLogPublisher(),
                feedback_recorder=NoopFeedbackRecorder(),
                training_runs_table=training_runs_table,
                synonym_expander=NoopSynonymExpander(),
            )
        properties_table = (
            f"{settings.project_id}.{settings.bq_dataset_feature_mart}."
            f"{settings.bq_table_properties_cleaned}"
        )
        features_table = (
            f"{settings.project_id}.{settings.bq_dataset_feature_mart}."
            f"{settings.bq_table_property_features_daily}"
        )
        embeddings_table = (
            f"{settings.project_id}.{settings.bq_dataset_feature_mart}."
            f"{settings.bq_table_property_embeddings}"
        )
        ranking_log_table = f"{settings.project_id}.{settings.bq_dataset_mlops}.ranking_log"
        return InfraComponents(
            retrain_trigger_publisher=self.build_retrain_publisher(),
            retrain_queries=BigQueryRetrainQueries(
                client=self._context._bigquery(),
                training_runs_table=training_runs_table,
            ),
            data_catalog_reader=BigQueryDataCatalogReader(
                client=self._context._bigquery(),
                properties_table=properties_table,
                features_table=features_table,
                embeddings_table=embeddings_table,
                ranking_log_table=ranking_log_table,
                training_runs_table=training_runs_table,
            ),
            ranking_log_publisher=self.build_ranking_log_publisher(),
            feedback_recorder=self.build_feedback_recorder(),
            training_runs_table=training_runs_table,
            synonym_expander=self.build_synonym_expander(),
        )

    def build_retrain_publisher(self) -> PredictionPublisher | None:
        settings = self._settings
        if not settings.enable_search:
            return None
        messaging = settings.messaging
        if not messaging.retrain_topic:
            return None
        return PubSubPublisher(project_id=settings.project_id, topic=messaging.retrain_topic)

    def build_ranking_log_publisher(self) -> RankingLogPublisher:
        settings = self._settings
        if not settings.enable_search:
            return NoopRankingLogPublisher()
        messaging = settings.messaging
        if not messaging.ranking_log_topic:
            return NoopRankingLogPublisher()
        return PubSubRankingLogPublisher(
            project_id=settings.project_id,
            topic=messaging.ranking_log_topic,
        )

    def build_feedback_recorder(self) -> FeedbackRecorder:
        settings = self._settings
        if not settings.enable_search:
            return NoopFeedbackRecorder()
        messaging = settings.messaging
        if not messaging.feedback_topic:
            return NoopFeedbackRecorder()
        return PubSubFeedbackRecorder(
            project_id=settings.project_id,
            topic=messaging.feedback_topic,
        )

    def build_synonym_expander(self) -> SynonymExpanderPort:
        """Phase 7 SYN-1 — wire Redis-backed synonym dictionary.

        Selection rules:

        - ``synonym_backend == "redis"`` *and* ``synonym_redis_url`` set →
          construct ``RedisSynonymExpander`` against Cloud Memorystore.
        - Otherwise → ``NoopSynonymExpander`` (Phase 5 / 6 default,
          ``query_text`` flows through unchanged).

        Connection failures degrade gracefully: the adapter is constructed
        even when the backend is unreachable; the first ``expand`` call
        catches the exception and returns the original query.
        """
        settings = self._settings
        synonym = settings.synonym
        if synonym.backend != "redis" or not synonym.redis_url:
            return NoopSynonymExpander()
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "redis package unavailable; synonym expansion disabled"
            )
            return NoopSynonymExpander()
        password = os.environ.get(synonym.redis_password_env) or None
        client = redis.from_url(  # type: ignore[no-untyped-call]
            synonym.redis_url,
            password=password,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            health_check_interval=30,
        )
        return RedisSynonymExpander(
            client=client,
            key_prefix=synonym.key_prefix,
            max_synonyms_per_token=synonym.max_synonyms_per_token,
        )
