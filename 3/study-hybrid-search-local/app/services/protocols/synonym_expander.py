"""Synonym dictionary lookup for lexical query expansion.

Phase 3 mirrors the Port that Phase 7 (canonical) defines. Architecture
diagram (Phase 7 `docs/architecture/01_仕様と設計.md` §2.2.1) places
``Syn[Redis 同義語辞書 (query expansion)]`` in the lexical lane between
the API and Meilisearch BM25. Implementations expand the user query with
synonyms (e.g. ``マンション`` → ``マンション アパート 共同住宅``) so BM25
recall improves without changing the semantic-side embedding.

The semantic side keeps the original query — multilingual-e5 already
handles synonymy natively, and expansion would dilute the embedding. So
``SearchService`` calls :meth:`expand` once and routes the expanded text
to lexical retrieval (``query_text``) while passing the original query
to the encoder.

Implementations MUST be defensive: any backend failure (network, decode,
missing keys) falls back to returning ``query`` as-is so the ``/search``
endpoint stays available even when the synonym backend is degraded.
"""

from __future__ import annotations

from typing import Protocol


class SynonymExpanderPort(Protocol):
    """Returns query text expanded with synonyms.

    Implementations: ``RedisSynonymExpander`` (Docker Redis container in
    Phase 3, Cloud Memorystore in Phase 4+) / ``NoopSynonymExpander``
    (returns query unchanged when the backend is disabled).
    """

    def expand(self, query: str) -> str: ...
