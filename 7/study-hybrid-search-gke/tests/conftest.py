"""Root-level test fixtures.

Phase A-3 — share a ``fake_container`` / ``fake_app`` / ``fake_client``
trio across the test suite so handler / service tests can run without
real GCP credentials, KServe endpoints, or Pub/Sub topics.

Design notes:
- ``Container`` is a frozen dataclass; we build it directly here rather
  than going through ``ContainerBuilder`` (which would try to construct
  GCP clients).
- All adapter slots get ``tests._fakes.*`` test doubles by default.
  Individual tests can request the lower-level fixtures (``fake_encoder``
  etc.) and inject custom variants by passing ``fake_container_factory``.
- The ``ApiSettings`` used here disables every flag
  (``BQML_POPULARITY_ENABLED`` etc.) so the Container stays stateless;
  tests that need a flag flipped should override the settings explicitly.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.composition_root import Container
from app.observability import Observability
from app.services.data_catalog_service import DataCatalogService
from app.services.feedback_service import FeedbackService
from app.services.model_metrics_service import ModelMetricsService, default_cases_path
from app.services.search_service import SearchService
from app.settings import ApiSettings
from tests._fakes import (
    InMemoryCandidateRetriever,
    InMemoryFeatureFetcher,
    InMemoryFeedbackRecorder,
    InMemoryRankingLogPublisher,
    MockPredictionPublisher,
    MockRerankerClient,
    StubEncoderClient,
    StubRetrainQueries,
)


class _StubDataCatalogReader:
    def read_snapshot(self):  # type: ignore[no-untyped-def]
        from app.services.protocols.data_catalog_reader import (
            DataCatalogSnapshot,
            DataCatalogTablePreview,
        )

        return DataCatalogSnapshot(
            tables=[
                DataCatalogTablePreview(
                    key="property_features_daily",
                    title="学習特徴量",
                    description="stub preview",
                    table_fqn="mlops-test.feature_mart.property_features_daily",
                    latest_marker="2026-04-27",
                    columns=["property_id", "rent"],
                    rows=[{"property_id": "p001", "rent": 100000}],
                )
            ]
        )


@pytest.fixture
def fake_settings() -> ApiSettings:
    """ApiSettings with feature flags off and topics empty.

    Hard-coded ``project_id="mlops-test"`` keeps the value visible in
    log messages without invoking real ADC.
    """
    return ApiSettings(
        project_id="mlops-test",
        enable_search=True,
        enable_rerank=False,
        bqml_popularity_enabled=False,
        ranking_log_topic="",
        feedback_topic="",
        retrain_topic="",
        meili_base_url="",
        kserve_encoder_url="",
        kserve_reranker_url="",
    )


@pytest.fixture
def fake_encoder() -> StubEncoderClient:
    return StubEncoderClient()


@pytest.fixture
def fake_reranker() -> MockRerankerClient:
    return MockRerankerClient()


@pytest.fixture
def fake_candidate_retriever() -> InMemoryCandidateRetriever:
    return InMemoryCandidateRetriever()


@pytest.fixture
def fake_ranking_log_publisher() -> InMemoryRankingLogPublisher:
    return InMemoryRankingLogPublisher()


@pytest.fixture
def fake_feedback_recorder() -> InMemoryFeedbackRecorder:
    return InMemoryFeedbackRecorder()


@pytest.fixture
def fake_retrain_queries() -> StubRetrainQueries:
    return StubRetrainQueries()


@pytest.fixture
def fake_retrain_publisher() -> MockPredictionPublisher:
    return MockPredictionPublisher()


@pytest.fixture
def fake_feature_fetcher() -> InMemoryFeatureFetcher:
    """Default ``feature_fetcher`` fixture — empty in-memory store.

    Tests that need fresh-feature merge behaviour can construct their own
    ``InMemoryFeatureFetcher(rows=...)`` and inject via
    ``fake_container_factory(feature_fetcher=...)``.
    """
    return InMemoryFeatureFetcher()


@pytest.fixture
def fake_container_factory(
    fake_settings: ApiSettings,
    fake_encoder: StubEncoderClient,
    fake_reranker: MockRerankerClient,
    fake_candidate_retriever: InMemoryCandidateRetriever,
    fake_ranking_log_publisher: InMemoryRankingLogPublisher,
    fake_feedback_recorder: InMemoryFeedbackRecorder,
    fake_retrain_queries: StubRetrainQueries,
    fake_retrain_publisher: MockPredictionPublisher,
) -> Callable[..., Container]:
    """Return a callable that builds a Container, accepting overrides.

    Use it from tests when default fakes do not fit::

        def test_x(fake_container_factory):
            container = fake_container_factory(reranker_client=None)
            ...

    Any keyword not provided falls back to the per-fixture default.
    """

    def _build(**overrides: Any) -> Container:
        defaults: dict[str, Any] = {
            "settings": fake_settings,
            "observability": Observability.for_test(),
            "training_runs_table": "mlops-test.mlops.training_runs",
            "retrain_trigger_publisher": fake_retrain_publisher,
            "retrain_queries": fake_retrain_queries,
            "candidate_retriever": fake_candidate_retriever,
            "encoder_client": fake_encoder,
            "encoder_model_path": "stub-encoder",
            "reranker_client": fake_reranker,
            "model_path": "stub-reranker",
            "popularity_scorer": None,
            "ranking_log_publisher": fake_ranking_log_publisher,
            "feedback_recorder": fake_feedback_recorder,
            "feature_fetcher": None,  # PR-4 default off — preserves Phase 5 behaviour
        }
        defaults.update(overrides)
        # Build SearchService / FeedbackService from the composed adapters so
        # handler tests see the full stack.
        defaults.setdefault(
            "search_service",
            SearchService(
                retriever_default=defaults["candidate_retriever"],
                encoder=defaults["encoder_client"],
                publisher=defaults["ranking_log_publisher"],
                reranker=defaults["reranker_client"],
                popularity_scorer=defaults["popularity_scorer"],
                feature_fetcher=defaults["feature_fetcher"],
            ),
        )
        defaults.setdefault(
            "feedback_service",
            FeedbackService(recorder=defaults["feedback_recorder"]),
        )
        defaults.setdefault(
            "model_metrics_service",
            ModelMetricsService(
                search_service=defaults["search_service"],
                default_cases_file=default_cases_path(),
            ),
        )
        defaults.setdefault(
            "data_catalog_service",
            DataCatalogService(reader=_StubDataCatalogReader()),
        )
        return Container(**defaults)

    return _build


@pytest.fixture
def fake_container(
    fake_container_factory: Callable[..., Container],
) -> Container:
    return fake_container_factory()


@pytest.fixture
def fake_app(fake_container: Container) -> FastAPI:
    """A bare FastAPI app with handlers wired to ``fake_container``.

    Mirrors ``app.main.create_app`` minus middleware / static / templates
    so handler tests stay focused on JSON I/O.
    """
    from app.api.routers import (
        feedback_router,
        health_router,
        retrain_router,
        search_router,
    )

    app = FastAPI()
    app.state.container = fake_container
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(feedback_router)
    app.include_router(retrain_router)
    return app


@pytest.fixture
def fake_client(fake_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(fake_app) as client:
        yield client
