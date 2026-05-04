"""HTTP-level fixtures for ``tests/unit/app/``.

Builds a FastAPI app whose handler stack mirrors ``create_app()`` but
runs against a fake Container (no real GCP / KServe). Tests reach the
container via ``request.app.state.container`` like production handlers.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware import RequestLoggingMiddleware
from app.api.routers import (
    feedback_router,
    health_router,
    retrain_router,
    search_router,
)
from app.domain.candidate import Candidate
from ml.common.logging import get_logger


@pytest.fixture
def app_with_search_stub(
    fake_container_factory: Callable[..., object],
) -> FastAPI:
    """FastAPI app using the new DI container, with old state mirrors."""
    container = fake_container_factory(
        reranker_client=None,
        model_path=None,
    )
    candidate_retriever = container.candidate_retriever
    if candidate_retriever is not None and hasattr(candidate_retriever, "_candidates"):
        candidate_retriever._candidates = [
            Candidate(
                property_id=f"P-{i:03d}",
                lexical_rank=i,
                semantic_rank=i,
                me5_score=0.9 - 0.1 * i,
                property_features={
                    "rent": 100_000 + 1000 * i,
                    "walk_min": 5 + i,
                    "age_years": 10,
                    "area_m2": 30.0,
                    "ctr": 0.1,
                    "fav_rate": 0.02,
                    "inquiry_rate": 0.01,
                },
            )
            for i in range(1, 4)
        ]
    app = FastAPI()
    app.state.container = container
    app.add_middleware(RequestLoggingMiddleware, logger=get_logger("app"))
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(feedback_router)
    app.include_router(retrain_router)
    return app


@pytest.fixture
def search_client(app_with_search_stub: FastAPI) -> TestClient:
    with TestClient(app_with_search_stub) as client:
        yield client
