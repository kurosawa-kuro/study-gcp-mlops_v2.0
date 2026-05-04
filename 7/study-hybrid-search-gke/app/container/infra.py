"""Infrastructure-facing dependency assembly.

This module owns Pub/Sub and query-side support objects that are shared
across API services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.adapters import (
    BigQueryDataCatalogReader,
    BigQueryRetrainQueries,
    PubSubFeedbackRecorder,
    PubSubPublisher,
    PubSubRankingLogPublisher,
)
from app.services.noop_adapters import (
    NoopDataCatalogReader,
    NoopFeedbackRecorder,
    NoopRankingLogPublisher,
    NoopRetrainQueries,
)
from app.services.protocols import (
    DataCatalogReader,
    FeedbackRecorder,
    PredictionPublisher,
    RankingLogPublisher,
)
from app.services.protocols.retrain_queries import RetrainQueries
from app.settings import ApiSettings


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
