"""Deterministic in-memory ``LexicalSearchPort`` stub."""

from __future__ import annotations

from typing import Any

from app.domain.retrieval import LexicalResult
from app.services.protocols.lexical_search import LexicalSearchPort


class InMemoryLexicalSearch(LexicalSearchPort):
    """Returns a configured rank list, optionally filtered by query length.

    ``ranked_ids`` is the canonical lexical order; the adapter slices it
    to ``top_k``. Service-layer tests rarely care about the concrete
    BM25 logic, so this stub just hands back what the test wants.
    """

    def __init__(self, *, ranked_ids: list[str] | None = None) -> None:
        self._ranked_ids = list(ranked_ids or [])
        self.calls: list[_LexicalCall] = []

    def search(
        self,
        *,
        query: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> list[LexicalResult]:
        self.calls.append(_LexicalCall(query=query, filters=dict(filters), top_k=top_k))
        return [
            LexicalResult(property_id=pid, rank=idx + 1)
            for idx, pid in enumerate(self._ranked_ids[:top_k])
        ]


class _LexicalCall:
    __slots__ = ("filters", "query", "top_k")

    def __init__(self, *, query: str, filters: dict[str, Any], top_k: int) -> None:
        self.query = query
        self.filters = filters
        self.top_k = top_k
