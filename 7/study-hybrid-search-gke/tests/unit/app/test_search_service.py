"""Unit tests for ``SearchService`` orchestration.

Phase D-1 introduced ``SearchService`` as the inbound use-case. These
tests exercise the orchestration through Port mocks (``tests.fakes``)
without standing up FastAPI / Pydantic / GCP. The HTTP-level integration
sits in ``test_search_handler_http.py``.
"""

from __future__ import annotations

import pytest

from app.domain.candidate import Candidate
from app.domain.search import SearchInput
from app.services.search_service import SearchService, SearchServiceUnavailable
from tests._fakes import (
    InMemoryCandidateRetriever,
    InMemoryRankingLogPublisher,
    MockRerankerClient,
    StubEncoderClient,
    StubPopularityScorer,
)


def _make_candidate(property_id: str, lexical_rank: int, semantic_rank: int) -> Candidate:
    return Candidate(
        property_id=property_id,
        lexical_rank=lexical_rank,
        semantic_rank=semantic_rank,
        me5_score=0.5,
        property_features={
            "rent": 100000,
            "walk_min": 5,
            "age_years": 10,
            "area_m2": 25.0,
            "ctr": 0.1,
            "fav_rate": 0.05,
            "inquiry_rate": 0.02,
            "rrf_rank": lexical_rank,
        },
    )


def _build_service(
    *,
    candidates: list[Candidate] | None = None,
    reranker: MockRerankerClient | None = None,
    popularity_scorer: StubPopularityScorer | None = None,
) -> tuple[SearchService, dict[str, object]]:
    retriever = InMemoryCandidateRetriever(candidates=candidates)
    encoder = StubEncoderClient()
    publisher = InMemoryRankingLogPublisher()
    service = SearchService(
        retriever_default=retriever,
        encoder=encoder,
        publisher=publisher,
        reranker=reranker,
        popularity_scorer=popularity_scorer,
    )
    deps: dict[str, object] = {
        "retriever": retriever,
        "encoder": encoder,
        "publisher": publisher,
        "reranker": reranker,
        "popularity_scorer": popularity_scorer,
    }
    return service, deps


def test_search_returns_items_sorted_by_final_rank() -> None:
    candidates = [
        _make_candidate("P-001", lexical_rank=2, semantic_rank=2),
        _make_candidate("P-002", lexical_rank=1, semantic_rank=1),
    ]
    service, _ = _build_service(candidates=candidates)
    output = service.search(
        request_id="req-1",
        input=SearchInput(query="渋谷 1LDK", filters={}, top_k=5),
    )
    assert [item.property_id for item in output.items] == ["P-002", "P-001"]
    assert [item.final_rank for item in output.items] == [1, 2]


def test_search_calls_publisher_once_with_full_pool() -> None:
    candidates = [
        _make_candidate(f"P-{i:03d}", lexical_rank=i, semantic_rank=i) for i in range(1, 4)
    ]
    service, deps = _build_service(candidates=candidates)
    service.search(
        request_id="req-2",
        input=SearchInput(query="池袋", filters={}, top_k=2),
    )
    publisher = deps["publisher"]
    assert isinstance(publisher, InMemoryRankingLogPublisher)
    # The in-memory retriever fake slices to top_k, so the publisher sees the
    # same truncated pool in this unit test.
    assert len(publisher.calls) == 1
    assert len(publisher.calls[0].candidates) == 2


def test_search_uses_reranker_scores_when_available() -> None:
    candidates = [
        _make_candidate("P-001", lexical_rank=1, semantic_rank=1),
        _make_candidate("P-002", lexical_rank=2, semantic_rank=2),
    ]
    reranker = MockRerankerClient()
    # MockRerankerClient default returns [1.0, 0.9] for 2 instances → P-001
    # gets the higher score and stays #1.
    service, _ = _build_service(candidates=candidates, reranker=reranker)
    output = service.search(
        request_id="req-3",
        input=SearchInput(query="池袋", filters={}, top_k=5),
    )
    assert [item.score for item in output.items] == [1.0, 0.9]
    assert reranker.predict_calls, "reranker.predict should have been called"


def test_search_raises_unavailable_when_retriever_missing() -> None:
    service = SearchService(
        retriever_default=None,
        encoder=StubEncoderClient(),
        publisher=InMemoryRankingLogPublisher(),
    )
    with pytest.raises(SearchServiceUnavailable):
        service.search(
            request_id="req-7",
            input=SearchInput(query="x", filters={}, top_k=1),
        )


def test_search_raises_unavailable_when_encoder_missing() -> None:
    service = SearchService(
        retriever_default=InMemoryCandidateRetriever(),
        encoder=None,
        publisher=InMemoryRankingLogPublisher(),
    )
    with pytest.raises(SearchServiceUnavailable):
        service.search(
            request_id="req-8",
            input=SearchInput(query="x", filters={}, top_k=1),
        )


def test_search_populates_popularity_score_when_scorer_present() -> None:
    candidates = [_make_candidate("P-001", lexical_rank=1, semantic_rank=1)]
    scorer = StubPopularityScorer(scores={"P-001": 0.42})
    service, _ = _build_service(candidates=candidates, popularity_scorer=scorer)
    output = service.search(
        request_id="req-10",
        input=SearchInput(query="x", filters={}, top_k=1),
    )
    assert output.items[0].popularity_score == 0.42
