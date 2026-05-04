"""ML-facing dependency assembly.

This module owns optional PMLE enrichments wired into the API container.
All returned objects are startup singletons.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.container.internal.optional_adapter import resolve_optional_adapter
from app.services.protocols.popularity_scorer import PopularityScorer
from app.settings import ApiSettings


class MlBuilderContext(Protocol):
    _settings: ApiSettings
    _logger: Any

    def _bigquery(self) -> Any: ...


@dataclass(frozen=True)
class MlComponents:
    popularity_scorer: PopularityScorer | None


class MlBuilder:
    def __init__(self, context: MlBuilderContext) -> None:
        self._context = context

    @property
    def _settings(self) -> ApiSettings:
        return self._context._settings

    @property
    def _logger(self) -> Any:
        return self._context._logger

    def build(self) -> MlComponents:
        return MlComponents(
            popularity_scorer=self.build_popularity_scorer(),
        )

    def build_popularity_scorer(self) -> PopularityScorer | None:
        settings = self._settings
        popularity = settings.popularity
        model_fqn = popularity.model_fqn or (
            f"{settings.project_id}.{settings.bq_dataset_mlops}.property_popularity"
        )
        properties_table = (
            f"{settings.project_id}.{settings.bq_dataset_feature_mart}."
            f"{settings.bq_table_properties_cleaned}"
        )
        features_table = (
            f"{settings.project_id}.{settings.bq_dataset_feature_mart}."
            f"{settings.bq_table_property_features_daily}"
        )

        def _factory() -> PopularityScorer:
            from app.services.adapters.bqml_popularity_scorer import BQMLPopularityScorer

            return BQMLPopularityScorer(
                project_id=settings.project_id,
                model_fqn=model_fqn,
                properties_table=properties_table,
                features_table=features_table,
                client=self._context._bigquery(),
            )

        return resolve_optional_adapter(
            name="BQML popularity scorer",
            enabled=popularity.enabled,
            factory=_factory,
            logger=self._logger,
        )
