"""``CandidateRetriever`` Port — hybrid lexical + semantic candidate retrieval.

Implementations: ``BigQueryCandidateRetriever`` (production; runs
Meilisearch for BM25, BigQuery ``VECTOR_SEARCH`` for semantic, then
RRF-fuses and enriches with property features from BigQuery).

Failure semantics: implementations raise on transient backend failures
(empty result is allowed and represented by an empty list). The service
layer is responsible for converting to HTTP 503 / 5xx as appropriate.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.candidate import Candidate
from app.domain.search import SearchFilters


class CandidateRetriever(Protocol):
    """Hybrid retrieval Port.

    ``query_vector`` is the multilingual-e5 embedding of ``query_text``
    (encoder responsibility, see ``EncoderClient``). The retriever fuses
    lexical + semantic results via RRF then enriches each property_id with
    ``property_features`` (rent, walk_min, age_years, area_m2, ctr, ...)
    pulled from ``properties_cleaned`` / ``property_features_daily``.

    The list is bounded by ``top_k`` after RRF fusion; lexical/semantic
    backends fetch their own internal candidate counts (typically larger
    than ``top_k``) before fusion.

    ``filters`` is a ``SearchFilters`` TypedDict (Phase B-4). At runtime
    it is a plain dict, so adapters that look up keys defensively keep
    working unchanged.
    """

    def retrieve(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        filters: SearchFilters,
        top_k: int,
    ) -> list[Candidate]: ...
