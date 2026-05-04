"""Happy-path tests for RequestLoggingMiddleware.

Exercised via the FastAPI TestClient against /healthz (always available)
and /search (requires the search-stub fixture).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_middleware_generates_request_id_when_absent(search_client) -> None:
    r = search_client.get("/healthz")
    assert r.status_code == 200
    rid = r.headers.get("x-request-id")
    assert rid and len(rid) >= 16


def test_middleware_preserves_client_supplied_request_id(search_client) -> None:
    r = search_client.get("/healthz", headers={"x-request-id": "req-abc-123"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "req-abc-123"


def test_middleware_request_id_matches_search_response(app_with_search_stub) -> None:
    with TestClient(app_with_search_stub) as client:
        r = client.post(
            "/search",
            json={"query": "test", "top_k": 1},
            headers={"x-request-id": "my-trace"},
        )
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "my-trace"
    assert r.json()["request_id"] == "my-trace"
