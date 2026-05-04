"""Phase 6 T4 unit tests.

* **T4 (Explainable AI)** — ``run_search(want_explanations=True)`` returns
  attributions when the reranker satisfies ``RerankerExplainer``, and
  silently falls back to ``None`` otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.candidate import Candidate
from app.services.ranking import run_search


@dataclass
class _FakeRetriever:
    candidates: list[Candidate]

    def retrieve(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        filters: dict[str, Any],
        top_k: int,
    ) -> list[Candidate]:
        return list(self.candidates)


@dataclass
class _FakePublisher:
    calls: list[dict[str, Any]] = field(default_factory=list)

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
                "final_ranks": list(final_ranks),
                "scores": list(scores),
                "model_path": model_path,
            }
        )


class _PlainReranker:
    """Only predict(); no predict_with_explain -> should fall back."""

    def predict(self, instances: list[list[float]]) -> list[float]:
        return [float(idx) for idx in range(len(instances))]


class _ExplainReranker:
    """RerankerExplainer satisfier. Returns both scores + attributions."""

    def predict(self, instances: list[list[float]]) -> list[float]:
        return [float(idx) for idx in range(len(instances))]

    def predict_with_explain(
        self,
        instances: list[list[float]],
        feature_names: list[str],
    ) -> tuple[list[float], list[dict[str, float]]]:
        scores = [float(idx) for idx in range(len(instances))]
        attributions = [
            {name: 0.1 * (idx + 1) for name in feature_names} | {"_baseline": 0.0}
            for idx, _ in enumerate(instances)
        ]
        return scores, attributions


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


def test_run_search_returns_attributions_when_reranker_supports_explain() -> None:
    candidates = [_candidate(i) for i in range(1, 4)]
    retriever = _FakeRetriever(candidates=candidates)
    publisher = _FakePublisher()

    ranked = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-1",
        query_text="query",
        query_vector=[0.0] * 4,
        filters={},
        top_k=5,
        reranker=_ExplainReranker(),
        model_path="gs://models/v1",
        want_explanations=True,
    )

    assert len(ranked) == 3
    assert all(item.attributions is not None for item in ranked)
    any_row = next(iter(ranked)).attributions
    assert any_row is not None
    assert "rent" in any_row
    assert "me5_score" in any_row
    assert "_baseline" in any_row


def test_run_search_falls_back_to_no_attributions_when_reranker_lacks_explain() -> None:
    candidates = [_candidate(i) for i in range(1, 4)]
    retriever = _FakeRetriever(candidates=candidates)
    publisher = _FakePublisher()

    ranked = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="req-2",
        query_text="query",
        query_vector=[0.0] * 4,
        filters={},
        top_k=5,
        reranker=_PlainReranker(),
        model_path=None,
        want_explanations=True,
    )

    assert len(ranked) == 3
    assert all(item.attributions is None for item in ranked)
