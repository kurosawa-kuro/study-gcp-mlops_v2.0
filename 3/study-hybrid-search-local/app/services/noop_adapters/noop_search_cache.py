"""Null ``SearchCachePort`` — every call is a MISS.

Selected when ``search_cache_backend=none`` or the Redis URL is empty.
``/search`` then runs end-to-end on every request, matching the Phase 3
Wave 1-4 behaviour exactly.
"""

from __future__ import annotations

from app.domain.search import SearchInput, SearchOutput
from app.services.protocols.search_cache import SearchCachePort


class NoopSearchCache(SearchCachePort):
    def get(self, request: SearchInput) -> SearchOutput | None:
        return None

    def set(self, request: SearchInput, output: SearchOutput) -> None:
        return None
