"""Deterministic ``PopularityScorer`` stub for Phase 6 T1 tests."""

from __future__ import annotations

from app.services.protocols.popularity_scorer import PopularityScorer


class StubPopularityScorer(PopularityScorer):
    def __init__(self, *, scores: dict[str, float] | None = None) -> None:
        self._scores = dict(scores or {})
        self.calls: list[list[str]] = []

    def score(self, property_ids: list[str]) -> dict[str, float]:
        self.calls.append(list(property_ids))
        return {pid: self._scores.get(pid, 0.0) for pid in property_ids}
