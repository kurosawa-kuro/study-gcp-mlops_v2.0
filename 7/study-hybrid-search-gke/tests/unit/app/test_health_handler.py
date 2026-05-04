"""HTTP-level tests for /livez /healthz /readyz."""

from __future__ import annotations


def test_livez_returns_ok(fake_client) -> None:
    response = fake_client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_returns_ok(fake_client) -> None:
    response = fake_client.get("/healthz")
    assert response.status_code == 200


def test_readyz_returns_ready_when_search_wired(fake_client) -> None:
    response = fake_client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["search_enabled"] is True


def test_readyz_returns_loading_when_retriever_missing(fake_client, fake_app) -> None:
    container = fake_app.state.container
    new_container = type(container)(**{**container.__dict__, "candidate_retriever": None})
    fake_app.state.container = new_container

    response = fake_client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "loading"
