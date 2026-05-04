"""Lexical retrieval abstraction (BM25-side candidate fetch).

Phase B-4 narrowed the return type from ``list[tuple[str, int]]`` to
``list[LexicalResult]`` (NamedTuple) and the filter type from
``dict[str, Any]`` to ``SearchFilters`` (TypedDict). NamedTuple subclasses
``tuple`` so existing adapter implementations returning plain tuples
remain compatible at runtime.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.retrieval import LexicalResult
from app.domain.search import SearchFilters


class LexicalSearchPort(Protocol):
    """Returns lexical rank list as ``(property_id, rank)`` named tuples.

    Implementations: ``MeilisearchLexical`` (Cloud Run BM25) /
    ``NoopLexicalSearch`` (when ``MEILI_BASE_URL`` is empty).
    """

    def search(
        self,
        *,
        query: str,
        filters: SearchFilters,
        top_k: int,
    ) -> list[LexicalResult]: ...
