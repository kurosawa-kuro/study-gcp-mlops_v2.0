"""``SearchCachePort`` — caches ``/search`` responses keyed on the request.

Phase 3 SYN-2 (companion of SYN-1 synonym dictionary). Where the synonym
dictionary improves *quality* (BM25 recall), the response cache improves
*UX / latency* by skipping the lexical + semantic + RRF + LightGBM
pipeline for repeat queries inside a short TTL window.

Design contract (kept identical to the future Phase 7 SYN-2 adapter so
adapter swap is the only Phase 4+ work needed):

- Misses → return ``None``. ``SearchService`` falls through to live search.
- Failures → also return ``None`` (and log). The cache is best-effort —
  it must never break ``/search`` availability.
- TTL is a property of the *adapter* (set at construction), not a per-call
  argument. This keeps the Port narrow and lets ops change TTL without
  touching service code.
- Cached payload intentionally excludes ``request_id`` (callers stamp the
  current one) and ``ranked`` (see :class:`app.domain.search.SearchOutput`
  for why ``ranked`` is unnecessary on cache HIT — ``ranking_log`` was
  already published on the original MISS so re-publishing would create
  duplicate rows).
- Cached payload is keyed on ``(query, filters, top_k, explain)``. Any
  user-segment / personalization key MUST be added here before caching
  per-user results — see the Port docstring in ``synonym_expander.py`` for
  the equivalent rationale.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.search import SearchInput, SearchOutput


class SearchCachePort(Protocol):
    """Read / write ``/search`` responses keyed on :class:`SearchInput`.

    Implementations: ``RedisSearchCache`` (Docker Compose / Cloud Memorystore)
    / ``NoopSearchCache`` (cache disabled — every call is a MISS).
    """

    def get(self, request: SearchInput) -> SearchOutput | None: ...

    def set(self, request: SearchInput, output: SearchOutput) -> None: ...
