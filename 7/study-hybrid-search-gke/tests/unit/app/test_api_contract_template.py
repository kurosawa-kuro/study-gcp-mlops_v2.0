"""Cross-phase API contract template tests for /search /feedback /readyz."""

from __future__ import annotations

from dataclasses import replace

from app.services.search_service import SearchService


def _search_payload() -> dict:
    return {
        "query": "赤羽駅徒歩10分 ペット可",
        "filters": {"max_rent": 150_000, "pet_ok": True},
        "top_k": 3,
    }


def _assert_search_shape(body: dict) -> None:
    assert "request_id" in body
    results = body.get("results")
    assert isinstance(results, list)
    assert len(results) > 0


def _assert_trace_identifier(body: dict) -> None:
    assert isinstance(body.get("request_id"), str)
    assert body["request_id"].strip() != ""


def _assert_result_item_required_fields(body: dict) -> None:
    first = body["results"][0]
    for key in ("property_id", "final_rank", "lexical_rank", "semantic_rank", "me5_score"):
        assert key in first


def _assert_feedback_shape(body: dict) -> None:
    assert body == {"accepted": True}


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


def test_api_contract_readyz_returns_ok(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json().get("status") == "ready"


def test_api_contract_search_success_shape(search_client) -> None:
    r = search_client.post("/search", json=_search_payload())
    assert r.status_code == 200
    _assert_search_shape(r.json())


def test_api_contract_search_has_trace_identifier(search_client) -> None:
    r = search_client.post("/search", json=_search_payload())
    assert r.status_code == 200
    _assert_trace_identifier(r.json())


def test_api_contract_search_result_item_required_fields(search_client) -> None:
    r = search_client.post("/search", json=_search_payload())
    assert r.status_code == 200
    _assert_result_item_required_fields(r.json())


def test_api_contract_feedback_accepts_click(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        r = client.post(
            "/feedback",
            json={"request_id": "abc", "property_id": "P-001", "action": "click"},
        )
    assert r.status_code == 200
    _assert_feedback_shape(r.json())


def test_api_contract_search_validation_error(search_client) -> None:
    payload = _search_payload()
    payload["query"] = ""
    r = search_client.post("/search", json=payload)
    assert r.status_code == 422


def test_api_contract_feedback_rejects_unknown_action(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        r = client.post(
            "/feedback",
            json={"request_id": "abc", "property_id": "P-001", "action": "teleport"},
        )
    assert r.status_code == 422


def test_api_contract_feedback_validation_error(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_with_search_stub) as client:
        # Missing required field `property_id`.
        r = client.post("/feedback", json={"request_id": "abc", "action": "click"})
    assert r.status_code == 422


def test_api_contract_search_unavailable_behavior(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    _replace_search_container(app_with_search_stub, encoder_client=None)
    with TestClient(app_with_search_stub) as client:
        r = client.post("/search", json=_search_payload())
    assert r.status_code == 503
