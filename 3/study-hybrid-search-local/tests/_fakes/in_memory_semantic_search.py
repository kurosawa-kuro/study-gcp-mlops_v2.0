"""Deterministic in-memory ``SemanticSearchPort`` stub."""

from __future__ import annotations

from typing import Any

from app.domain.retrieval import SemanticResult
from app.services.protocols.semantic_search import SemanticSearchPort


class InMemorySemanticSearch(SemanticSearchPort):
    """Returns a fixed (property_id, similarity) sequence in input order.

    Each entry's ``rank`` is assigned from 1, ``similarity`` is taken
    from the configured score map (default 1.0).
    """

    def __init__(
        self,
        *,
        ranked_ids: list[str] | None = None,
        similarity_by_id: dict[str, float] | None = None,
    ) -> None:
        self._ranked_ids = list(ranked_ids or [])
        self._similarity_by_id = dict(similarity_by_id or {})
        self.calls: list[_SemanticCall] = []

    def search(
        self,
        *,
        query_vector: list[float],
        filters: dict[str, Any],
        top_k: int,
    ) -> list[SemanticResult]:
        self.calls.append(
            _SemanticCall(query_vector=list(query_vector), filters=dict(filters), top_k=top_k)
        )
        out: list[SemanticResult] = []
        for idx, pid in enumerate(self._ranked_ids[:top_k], start=1):
            sim = self._similarity_by_id.get(pid, 1.0)
            out.append(SemanticResult(property_id=pid, rank=idx, similarity=sim))
        return out


class _SemanticCall:
    __slots__ = ("filters", "query_vector", "top_k")

    def __init__(self, *, query_vector: list[float], filters: dict[str, Any], top_k: int) -> None:
        self.query_vector = query_vector
        self.filters = filters
        self.top_k = top_k
