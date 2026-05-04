"""Domain models for retrieved + ranked search candidates.

``Candidate`` is what the lexical / semantic retrieval step yields, before
reranking. ``RankedCandidate`` is what the search service returns after
optional reranking. Both are immutable dataclasses so they can be freely
shared across service / handler / mapper layers without aliasing risk.

Phase B-1 moved these out of ``app/services/protocols/candidate_retriever.py``
where they were co-mingled with three Protocols. Ports now reference these
domain types in their signatures (e.g. ``CandidateRetriever.retrieve ->
list[Candidate]``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Candidate:
    """One candidate property returned from the lexical / vector search step.

    ``property_features`` carries the raw feature dict pulled from BigQuery
    (rent / walk_min / age_years / area_m2 / ctr / ...) and is consumed by
    ``ml.data.feature_engineering.build_ranker_features`` during reranking.
    Kept as ``dict[str, Any]`` because the feature schema evolves alongside
    the ranker (parity invariant; see `CLAUDE.md`).
    """

    property_id: str
    # BM25-side rank from lexical retrieval (Meilisearch).
    lexical_rank: int
    # VECTOR_SEARCH-side rank from semantic retrieval (BigQuery).
    semantic_rank: int
    me5_score: float
    property_features: dict[str, Any]


@dataclass(frozen=True)
class RankedCandidate:
    """Reranked candidate with optional explanation attributions.

    ``score`` is ``None`` in Phase 4 fallback mode (rerank disabled); each
    entry matches the candidate by index in rerank mode. ``attributions``
    is populated only when the caller passes ``want_explanations=True`` AND
    the reranker satisfies ``RerankerExplainer`` (Phase 6 T4 TreeSHAP path).
    """

    candidate: Candidate
    final_rank: int
    score: float | None
    attributions: dict[str, float] | None = None
