"""HTTP-level tests for the ``/search`` handler.

Phase D-2 / Phase A-2 — exercises the full Depends() injection path
(``get_container`` → Container → SearchService) using the ``fake_app``
fixture from ``tests/conftest.py``.
"""

from __future__ import annotations

from app.domain.candidate import Candidate


def _candidate(property_id: str, lex: int, sem: int) -> Candidate:
    return Candidate(
        property_id=property_id,
        lexical_rank=lex,
        semantic_rank=sem,
        me5_score=0.4,
        property_features={
            "title": f"{property_id} の物件",
            "city": "東京",
            "ward": "北区",
            "layout": "1LDK",
            "rent": 120000,
            "walk_min": 7,
            "age_years": 12,
            "area_m2": 28.0,
            "pet_ok": True,
        },
    )


def test_search_endpoint_returns_results(fake_client, fake_candidate_retriever) -> None:
    fake_candidate_retriever._candidates = [
        _candidate("P-001", lex=1, sem=1),
        _candidate("P-002", lex=2, sem=2),
    ]

    response = fake_client.post(
        "/search",
        json={"query": "渋谷", "filters": {"max_rent": 200000}, "top_k": 5},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_id"]
    assert [item["property_id"] for item in body["results"]] == ["P-001", "P-002"]
    assert body["results"][0]["title"] == "P-001 の物件"
    assert body["results"][0]["ward"] == "北区"
    assert body["results"][0]["pet_ok"] is True


def test_search_endpoint_503_when_retriever_unavailable(
    fake_client,
    fake_app,
) -> None:
    # Replace the container with one that has no candidate retriever.
    container = fake_app.state.container
    # Rebuild SearchService to reflect the missing retriever.
    from app.services.search_service import SearchService

    new_search_service = SearchService(
        retriever_default=None,
        encoder=container.encoder_client,
        publisher=container.ranking_log_publisher,
    )
    new_container = type(container)(
        **{
            **container.__dict__,
            "candidate_retriever": None,
            "search_service": new_search_service,
        }
    )
    fake_app.state.container = new_container

    response = fake_client.post(
        "/search",
        json={"query": "x", "filters": {}, "top_k": 1},
    )

    assert response.status_code == 503


def test_search_endpoint_explain_returns_attributions(
    fake_client,
    fake_candidate_retriever,
) -> None:
    fake_candidate_retriever._candidates = [_candidate("P-EX", lex=1, sem=1)]

    response = fake_client.post(
        "/search?explain=true",
        json={"query": "x", "filters": {}, "top_k": 1},
    )

    assert response.status_code == 200, response.text
    item = response.json()["results"][0]
    # MockRerankerClient.predict_with_explain returns flat 1/N attributions
    assert item["attributions"] is not None
    assert "_baseline" in item["attributions"]
