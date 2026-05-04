"""Local boot contract for ``ENABLE_SEARCH=false``.

The app must be able to build its immutable container without ADC, BigQuery,
or Pub/Sub when search is explicitly disabled. Otherwise even `/livez`
verification becomes environment-dependent and the Phase 7 workflow contract
cannot be trusted.
"""

from __future__ import annotations

import pytest

from app.composition_root import ContainerBuilder
from app.services.noop_adapters import (
    NoopDataCatalogReader,
    NoopFeedbackRecorder,
    NoopRankingLogPublisher,
    NoopRetrainQueries,
)
from app.settings import ApiSettings


def test_container_builder_avoids_gcp_clients_when_search_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ApiSettings(
        project_id="mlops-test",
        enable_search=False,
        enable_rerank=False,
    )

    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("ENABLE_SEARCH=false must not initialize external clients")

    monkeypatch.setattr(ContainerBuilder, "_bigquery", _forbidden)
    monkeypatch.setattr("app.container.infra.PubSubPublisher", _forbidden)
    monkeypatch.setattr("app.container.infra.PubSubRankingLogPublisher", _forbidden)
    monkeypatch.setattr("app.container.infra.PubSubFeedbackRecorder", _forbidden)

    container = ContainerBuilder(settings).build()

    assert container.settings.enable_search is False
    assert container.candidate_retriever is None
    assert container.encoder_client is None
    assert container.feature_fetcher is None
    assert container.retrain_trigger_publisher is None
    assert isinstance(container.retrain_queries, NoopRetrainQueries)
    assert isinstance(container.ranking_log_publisher, NoopRankingLogPublisher)
    assert isinstance(container.feedback_recorder, NoopFeedbackRecorder)
    assert isinstance(container.data_catalog_service._reader, NoopDataCatalogReader)
