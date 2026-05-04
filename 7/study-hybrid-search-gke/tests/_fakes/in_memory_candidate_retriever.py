"""In-memory ``CandidateRetriever`` returning a fixed candidate list."""

from __future__ import annotations

from typing import Any

from app.domain.candidate import Candidate
from app.services.protocols.candidate_retriever import CandidateRetriever


class InMemoryCandidateRetriever(CandidateRetriever):
    """Returns a configured ``Candidate`` list, sliced to ``top_k``.

    Skips the lexical / semantic / RRF / BQ enrichment plumbing entirely
    so service-layer tests can focus on orchestration / ranking
    behaviour without standing up backing stores.
    """

    def __init__(self, *, candidates: list[Candidate] | None = None) -> None:
        self._candidates = list(candidates or [])
        self.calls: list[_RetrieveCall] = []

    def retrieve(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        filters: dict[str, Any],
        top_k: int,
    ) -> list[Candidate]:
        self.calls.append(
            _RetrieveCall(
                query_text=query_text,
                query_vector=list(query_vector),
                filters=dict(filters),
                top_k=top_k,
            )
        )
        return list(self._candidates[:top_k])


class _RetrieveCall:
    __slots__ = ("filters", "query_text", "query_vector", "top_k")

    def __init__(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        filters: dict[str, Any],
        top_k: int,
    ) -> None:
        self.query_text = query_text
        self.query_vector = query_vector
        self.filters = filters
        self.top_k = top_k
