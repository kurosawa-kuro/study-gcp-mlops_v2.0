"""Null ``LexicalSearchPort`` — returns empty result list.

Selected when ``MEILI_BASE_URL`` is empty. Hybrid retrieval still runs the
semantic side; the RRF fusion falls back to semantic-only ordering.
"""

from __future__ import annotations

from app.domain.retrieval import LexicalResult
from app.domain.search import SearchFilters
from app.services.protocols.lexical_search import LexicalSearchPort


class NoopLexicalSearch(LexicalSearchPort):
    def search(
        self,
        *,
        query: str,
        filters: SearchFilters,
        top_k: int,
    ) -> list[LexicalResult]:
        return []
