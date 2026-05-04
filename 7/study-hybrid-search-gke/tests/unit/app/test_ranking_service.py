"""Pure-orchestration tests for ``app.services.ranking.run_search``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.domain.candidate import Candidate
from app.services.ranking import run_search


@dataclass
class _FakeRetriever:
    candidates: list[Candidate]
    calls: list[dict] = field(default_factory=list)

    def retrieve(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        filters: dict[str, Any],
        top_k: int,
    ) -> list[Candidate]:
        self.calls.append({"query_text": query_text, "filters": filters, "top_k": top_k})
        return list(self.candidates)


@dataclass
class _FakePublisher:
    calls: list[dict] = field(default_factory=list)

    def publish_candidates(
        self,
        *,
        request_id: str,
        candidates: list[Candidate],
        final_ranks: list[int],
        scores: list[float | None],
        model_path: str | None,
    ) -> None:
        self.calls.append(
            {
                "request_id": request_id,
                "candidates": list(candidates),
                "final_ranks": list(final_ranks),
                "scores": list(scores),
                "model_path": model_path,
            }
        )


class _StubReranker:
    """A minimal reranker stand-in that returns predictable scores."""

    def predict(self, instances: list[list[float]]) -> list[float]:
        return [-row[8] for row in instances]


def _candidate(i: int) -> Candidate:
    return Candidate(
        property_id=f"P-{i:03d}",
        lexical_rank=i,
        semantic_rank=i,
        me5_score=0.9 - 0.05 * i,
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


# -- Fallback (reranker=None) -------------------------------------------------


def test_run_search_preserves_lexical_order() -> None:
    retriever = _FakeRetriever(candidates=[_candidate(i) for i in range(1, 6)])
    publisher = _FakePublisher()
    out = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-1",
        query_text="駅近",
        query_vector=[0.1, 0.2],
        filters={"max_rent": 150_000},
        top_k=3,
    )
    assert [item.candidate.property_id for item in out] == ["P-001", "P-002", "P-003"]
    assert [item.final_rank for item in out] == [1, 2, 3]


def test_run_search_final_rank_equals_lexical_rank_without_reranker() -> None:
    retriever = _FakeRetriever(candidates=[_candidate(i) for i in range(1, 5)])
    publisher = _FakePublisher()
    run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-2",
        query_text="駅近",
        query_vector=[0.0],
        filters={},
        top_k=4,
    )
    call = publisher.calls[0]
    assert call["final_ranks"] == [1, 2, 3, 4]
    assert call["scores"] == [None, None, None, None]
    assert call["model_path"] is None


def test_run_search_continues_when_publisher_raises() -> None:
    """Publish failures must NOT propagate as 500 to /search users.

    Adapter-level (``PubSubRankingLogPublisher.publish_candidates``)
    raises with a loud ERROR log + IAM hint so ops sees the breakage.
    But ranking_log is observability — losing rows must not turn
    /search into a 500. ``ranking._safe_publish_candidates`` catches.
    """

    class _FailingPublisher:
        def __init__(self) -> None:
            self.attempts = 0

        def publish_candidates(self, **_kwargs: object) -> None:
            self.attempts += 1
            raise RuntimeError("simulated Pub/Sub topic permission denial")

    retriever = _FakeRetriever(candidates=[_candidate(i) for i in range(1, 4)])
    publisher = _FailingPublisher()
    out = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-degraded",
        query_text="駅近",
        query_vector=[0.0],
        filters={},
        top_k=2,
    )
    # Search still serves the user with results despite publisher failure.
    assert len(out) == 2
    # Publisher was actually attempted (we did not skip the side-effect).
    assert publisher.attempts == 1


def test_run_search_publishes_full_pool_not_just_top_k() -> None:
    retriever = _FakeRetriever(candidates=[_candidate(i) for i in range(1, 6)])
    publisher = _FakePublisher()
    out = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-3",
        query_text="駅近",
        query_vector=[0.0],
        filters={},
        top_k=2,
    )
    assert len(out) == 2
    assert len(publisher.calls[0]["candidates"]) == 5


def test_run_search_forwards_filters_to_retriever() -> None:
    retriever = _FakeRetriever(candidates=[])
    publisher = _FakePublisher()
    run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-5",
        query_text="駅近",
        query_vector=[0.0],
        filters={"max_rent": 200_000, "pet_ok": True, "layout": "2LDK"},
        top_k=5,
    )
    assert retriever.calls[0]["filters"] == {
        "max_rent": 200_000,
        "pet_ok": True,
        "layout": "2LDK",
    }


def test_run_search_empty_result() -> None:
    retriever = _FakeRetriever(candidates=[])
    publisher = _FakePublisher()
    out = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-6",
        query_text="駅近",
        query_vector=[0.0],
        filters={},
        top_k=10,
    )
    assert out == []
    # publisher is still called with empty lists for coherent offline eval
    assert publisher.calls[0]["final_ranks"] == []
    assert publisher.calls[0]["scores"] == []


# -- Vertex rerank -------------------------------------------------------------


def test_run_search_rerank_reverses_order_when_reranker_says_so() -> None:
    retriever = _FakeRetriever(candidates=[_candidate(i) for i in range(1, 5)])
    publisher = _FakePublisher()
    out = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-rr",
        query_text="駅近",
        query_vector=[0.0],
        filters={},
        top_k=4,
        reranker=_StubReranker(),
        model_path="projects/p/locations/l/endpoints/123",
    )
    assert [item.candidate.property_id for item in out] == ["P-001", "P-002", "P-003", "P-004"]
    assert [item.final_rank for item in out] == [1, 2, 3, 4]
    call = publisher.calls[0]
    assert [c.property_id for c in call["candidates"]] == ["P-001", "P-002", "P-003", "P-004"]
    assert all(isinstance(s, float) for s in call["scores"])
    assert call["model_path"] == "projects/p/locations/l/endpoints/123"


@pytest.mark.parametrize("top_k", [1, 2, 4])
def test_run_search_rerank_truncates_to_top_k(top_k: int) -> None:
    retriever = _FakeRetriever(candidates=[_candidate(i) for i in range(1, 5)])
    publisher = _FakePublisher()
    out = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-tk",
        query_text="駅近",
        query_vector=[0.0],
        filters={},
        top_k=top_k,
        reranker=_StubReranker(),
        model_path="projects/p/locations/l/endpoints/123",
    )
    assert len(out) == top_k
    # Full pool still published.
    assert len(publisher.calls[0]["candidates"]) == 4


def test_run_search_rerank_with_higher_score_wins() -> None:
    """Explicit score check: ensure higher reranker score produces rank=1."""

    class _ForceWinReranker:
        def predict(self, instances: list[list[float]]) -> list[float]:
            return [float(-i) for i in range(len(instances))]

    retriever = _FakeRetriever(candidates=[_candidate(i) for i in range(1, 4)])
    publisher = _FakePublisher()
    out = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-wins",
        query_text="駅近",
        query_vector=[0.0],
        filters={},
        top_k=3,
        reranker=_ForceWinReranker(),
        model_path="projects/p/locations/l/endpoints/999",
    )
    assert out[0].candidate.property_id == "P-001"
    assert out[0].final_rank == 1
