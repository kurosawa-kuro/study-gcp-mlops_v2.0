"""/search + /feedback endpoint tests — Phase 4 completion gate."""

from __future__ import annotations

from dataclasses import replace

from app.services.search_service import SearchService


def _search_payload() -> dict:
    return {
        "query": "赤羽駅徒歩10分 ペット可",
        "filters": {"max_rent": 150_000, "pet_ok": True},
        "top_k": 3,
    }


def _replace_search_container(app, **updates: object) -> None:
    container = replace(app.state.container, **updates)
    container = replace(
        container,
        search_service=SearchService(
            retriever_default=container.candidate_retriever,
            encoder=container.encoder_client,
            publisher=container.ranking_log_publisher,
            reranker=container.reranker_client,
            popularity_scorer=container.popularity_scorer,
        ),
    )
    app.state.container = container


def test_search_returns_200_with_results(search_client) -> None:
    r = search_client.post("/search", json=_search_payload())
    assert r.status_code == 200
    body = r.json()
    assert "request_id" in body
    assert len(body["results"]) == 3


def test_search_results_preserve_lexical_rank_when_rerank_disabled(search_client) -> None:
    """Fallback gate: final_rank == lexical_rank until reranker is wired."""
    r = search_client.post("/search", json=_search_payload())
    body = r.json()
    for item in body["results"]:
        assert item["final_rank"] == item["lexical_rank"]
        assert item["score"] is None


def test_search_emits_ranking_log(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        r = client.post("/search", json=_search_payload())
    assert r.status_code == 200
    publisher = app_with_search_stub.state.container.ranking_log_publisher
    assert len(publisher.calls) == 1
    call = publisher.calls[0]
    assert len(call.candidates) == 3
    assert call.final_ranks == (1, 2, 3)
    assert call.model_path is None


def test_search_top_k_truncates_response(search_client) -> None:
    payload = _search_payload()
    payload["top_k"] = 2
    r = search_client.post("/search", json=payload)
    assert r.status_code == 200
    assert len(r.json()["results"]) == 2


def test_search_rejects_empty_query(search_client) -> None:
    payload = _search_payload()
    payload["query"] = ""
    r = search_client.post("/search", json=payload)
    assert r.status_code == 422


def test_search_503_when_disabled(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    _replace_search_container(app_with_search_stub, encoder_client=None)
    with TestClient(app_with_search_stub) as client:
        r = client.post("/search", json=_search_payload())
    assert r.status_code == 503


def test_feedback_accepts_click(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        r = client.post(
            "/feedback",
            json={"request_id": "abc", "property_id": "P-001", "action": "click"},
        )
    assert r.status_code == 200
    assert r.json() == {"accepted": True}
    recorder = app_with_search_stub.state.container.feedback_recorder
    assert len(recorder.events) == 1
    assert recorder.events[0].request_id == "abc"
    assert recorder.events[0].property_id == "P-001"
    assert recorder.events[0].action == "click"


def test_feedback_rejects_unknown_action(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        r = client.post(
            "/feedback",
            json={"request_id": "abc", "property_id": "P-001", "action": "teleport"},
        )
    assert r.status_code == 422


def test_readyz_ok_when_search_enabled(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["search_enabled"] is True


def test_readyz_503_when_retriever_missing(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    _replace_search_container(app_with_search_stub, candidate_retriever=None)
    with TestClient(app_with_search_stub) as client:
        r = client.get("/readyz")
    assert r.status_code == 503


def test_readyz_503_when_encoder_missing(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    _replace_search_container(app_with_search_stub, encoder_client=None)
    with TestClient(app_with_search_stub) as client:
        r = client.get("/readyz")
    assert r.status_code == 503


def test_healthz_unconditional(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_reports_rerank_disabled_when_client_missing(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        body = client.get("/readyz").json()
    assert body["rerank_enabled"] is False
    assert body["model_path"] is None


def test_readyz_reports_rerank_enabled_when_client_set(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    class _StubReranker:
        model_path = "projects/p/locations/l/endpoints/123"

        def predict(self, instances: list[list[float]]) -> list[float]:
            return [-row[8] for row in instances]

    reranker = _StubReranker()
    _replace_search_container(
        app_with_search_stub,
        reranker_client=reranker,
        model_path=reranker.model_path,
    )
    with TestClient(app_with_search_stub) as client:
        body = client.get("/readyz").json()
    assert body["rerank_enabled"] is True
    assert body["model_path"] == "projects/p/locations/l/endpoints/123"


def test_search_returns_scores_when_reranker_loaded(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    class _StubReranker:
        model_path = "projects/p/locations/l/endpoints/456"

        def predict(self, instances: list[list[float]]) -> list[float]:
            return [-row[8] for row in instances]

    reranker = _StubReranker()
    _replace_search_container(
        app_with_search_stub,
        reranker_client=reranker,
        model_path=reranker.model_path,
    )

    with TestClient(app_with_search_stub) as client:
        r = client.post("/search", json=_search_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["model_path"] == "projects/p/locations/l/endpoints/456"
    for item in body["results"]:
        assert item["score"] is not None, "rerank-on must populate per-item score"


def test_ranking_log_receives_scores_when_reranker_loaded(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    class _StubReranker:
        model_path = "projects/p/locations/l/endpoints/789"

        def predict(self, instances: list[list[float]]) -> list[float]:
            return [-row[8] for row in instances]

    reranker = _StubReranker()
    _replace_search_container(
        app_with_search_stub,
        reranker_client=reranker,
        model_path=reranker.model_path,
    )
    with TestClient(app_with_search_stub) as client:
        client.post("/search", json=_search_payload())
    publisher = app_with_search_stub.state.container.ranking_log_publisher
    call = publisher.calls[-1]
    assert all(isinstance(s, float) for s in call.scores)
    assert call.model_path == "projects/p/locations/l/endpoints/789"
