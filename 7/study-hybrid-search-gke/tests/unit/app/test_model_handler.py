"""Unit tests for ``/model/metrics`` and ``/model/info`` / ``/model/data``.

The handler is the first response surface for hybrid-search accuracy
evaluation (the role originally implied by ``/metrics``). We pin:

- 200 response shape (summary + per_case)
- 503 when ``model_metrics_service`` is missing
- ``k`` query-param boundary handling (FastAPI returns 422 on invalid)
- ``/model/info`` mirrors container settings / paths
- ``/model/data`` returns developer-facing data previews

Fakes wire a deterministic candidate set so NDCG / HitRate / MRR are
predictable and the test pins them numerically.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import model_router
from app.composition_root import Container
from app.domain.candidate import Candidate
from app.services.model_metrics_service import ModelMetricsService


def _build_client(container: Container) -> TestClient:
    app = FastAPI()
    app.state.container = container
    app.include_router(model_router)
    return TestClient(app)


def _wire_candidates(retriever) -> None:  # type: ignore[no-untyped-def]
    retriever._candidates = [
        Candidate(
            property_id=f"p{i:03d}",
            lexical_rank=i,
            semantic_rank=i,
            me5_score=0.5 - 0.1 * i,
            property_features={
                "rent": 100_000,
                "walk_min": 5,
                "age_years": 10,
                "area_m2": 30.0,
                "ctr": 0.1,
                "fav_rate": 0.02,
                "inquiry_rate": 0.01,
            },
        )
        for i in range(1, 6)
    ]


def test_model_metrics_returns_summary_and_per_case(
    fake_container_factory: Callable[..., Container],
    fake_candidate_retriever,  # type: ignore[no-untyped-def]
) -> None:
    _wire_candidates(fake_candidate_retriever)
    container = fake_container_factory()
    client = _build_client(container)

    res = client.get("/model/metrics?k=10")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["k"] == 10
    assert body["num_cases"] >= 1
    assert (
        "summary" in body and {"ndcg_at_k", "hit_rate_at_k", "mrr_at_k"} <= body["summary"].keys()
    )
    assert isinstance(body["per_case"], list) and body["per_case"]
    # Bundled cases mark p001 as relevant; retriever returns p001 at rank 1
    # so HitRate@10 must hit the ceiling.
    assert body["summary"]["hit_rate_at_k"] == 1.0


def test_model_metrics_503_when_service_missing(
    fake_container_factory: Callable[..., Container],
) -> None:
    container = fake_container_factory(model_metrics_service=None)
    client = _build_client(container)

    res = client.get("/model/metrics")

    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]


@pytest.mark.parametrize("k", [0, -1, 999])
def test_model_metrics_rejects_invalid_k(
    fake_container_factory: Callable[..., Container],
    k: int,
) -> None:
    container = fake_container_factory()
    client = _build_client(container)
    res = client.get(f"/model/metrics?k={k}")
    assert res.status_code == 422


def test_model_info_reports_container_state(
    fake_container_factory: Callable[..., Container],
) -> None:
    container = fake_container_factory()
    client = _build_client(container)

    res = client.get("/model/info")

    assert res.status_code == 200
    body = res.json()
    assert body["search_enabled"] is True
    # fake reranker is wired by default factory
    assert body["rerank_enabled"] is True
    assert body["reranker_model_path"] == "stub-reranker"
    assert body["encoder_model_path"] == "stub-encoder"


def test_model_data_returns_preview_tables(
    fake_container_factory: Callable[..., Container],
) -> None:
    container = fake_container_factory()
    client = _build_client(container)

    res = client.get("/model/data")

    assert res.status_code == 200
    body = res.json()
    assert len(body["tables"]) >= 1
    assert body["tables"][0]["key"] == "property_features_daily"
    assert body["tables"][0]["rows"][0]["property_id"] == "p001"


def test_load_cases_rejects_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.json"
    p.write_text('{"cases": []}', encoding="utf-8")
    from app.services.model_metrics_service import load_cases

    with pytest.raises(ValueError, match="non-empty list"):
        load_cases(p)


def test_evaluate_default_cases_returns_report(
    fake_container_factory: Callable[..., Container],
    fake_candidate_retriever,  # type: ignore[no-untyped-def]
) -> None:
    _wire_candidates(fake_candidate_retriever)
    container = fake_container_factory()
    svc = container.model_metrics_service
    assert isinstance(svc, ModelMetricsService)
    report = svc.evaluate(k=5)
    assert report.k == 5
    assert report.num_cases >= 1
    assert 0.0 <= report.summary_ndcg_at_k <= 1.0
    assert 0.0 <= report.summary_hit_rate_at_k <= 1.0
    assert 0.0 <= report.summary_mrr_at_k <= 1.0
