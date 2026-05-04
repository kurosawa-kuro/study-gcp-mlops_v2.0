"""Port for semantic candidate-search backends.

Phase 6 T3 で `BigQueryCandidateRetriever` から抽出した Port。Phase 7 W2-8
で互換レイヤを撤去後、本 phase の唯一の実装は
`VertexVectorSearchSemanticSearch` (Matching Engine 経由)。Port は将来別
backend (例: Elasticsearch ANN / OpenSearch) を差し替える余地として残す。

Phase B-4 で戻り値型を `list[tuple[str, int, float]]` から
`list[SemanticResult]` (NamedTuple) に narrow 済。
"""

from __future__ import annotations

from typing import Protocol

from app.domain.retrieval import SemanticResult
from app.domain.search import SearchFilters


class SemanticSearchPort(Protocol):
    """Return semantic neighbours of ``query_vector`` as named-tuple records.

    ``rank`` is 1-based and matches the ``semantic_rank`` column on
    ``Candidate`` / ``ranking_log``. ``similarity`` is in ``[0, 1]`` with
    higher = more similar (Phase 5 stores ``1 - cosine_distance`` here).
    """

    def search(
        self,
        *,
        query_vector: list[float],
        filters: SearchFilters,
        top_k: int,
    ) -> list[SemanticResult]: ...
