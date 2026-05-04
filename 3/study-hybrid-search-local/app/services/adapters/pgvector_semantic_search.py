"""Phase 3 — pgvector semantic search adapter.

PostgreSQL + pgvector extension の `<=>` 演算子 (cosine distance) で ANN を実行する。

Phase 4 で BigQuery `VECTOR_SEARCH` に差し替え、Phase 7 完成版で Vertex Vector
Search に再差し替えする想定。Port (`SemanticSearchPort`) は不変。

`similarity` は ``1 - cosine_distance`` で [0, 1] に正規化する (Phase 5+ と同じ
意味論)。
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from app.domain.retrieval import SemanticResult
from app.domain.search import SearchFilters
from app.services.protocols.semantic_search import SemanticSearchPort
from ml.common import get_logger


class PgVectorSemanticSearch(SemanticSearchPort):
    """Cosine distance top-K search via pgvector."""

    def __init__(self, *, dsn: str, embeddings_table: str = "embeddings") -> None:
        self._dsn = dsn
        self._table = embeddings_table
        self._logger = get_logger("app.adapters.pgvector_semantic")

    def search(
        self,
        *,
        query_vector: list[float],
        filters: SearchFilters,
        top_k: int,
    ) -> list[SemanticResult]:
        where_clauses, params = _filter_clauses(filters)
        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

        # pgvector の `<=>` は cosine distance (0=同一, 2=逆方向)。
        # similarity = 1 - distance に変換して返す (LightGBM 特徴量と整合)。
        sql = f"""
            SELECT p.property_id, e.embedding <=> %s::vector AS distance
            FROM {self._table} AS e
            JOIN properties AS p ON e.property_id = p.property_id
            WHERE {where_sql}
            ORDER BY distance ASC
            LIMIT %s
        """
        vec_literal = _to_pgvector_literal(query_vector)
        bound: list[Any] = [vec_literal, *params, int(top_k)]

        out: list[SemanticResult] = []
        try:
            with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
                cur.execute(sql, bound)
                for rank, (property_id, distance) in enumerate(cur.fetchall(), start=1):
                    sim = max(0.0, 1.0 - float(distance))
                    out.append(
                        SemanticResult(
                            property_id=str(property_id),
                            rank=rank,
                            similarity=sim,
                        )
                    )
        except Exception:
            self._logger.exception("pgvector semantic search failed")
            return []
        return out


def _to_pgvector_literal(vec: list[float]) -> str:
    """pgvector は ``[0.1, 0.2, ...]`` リテラルを受け付ける。"""
    return json.dumps([float(x) for x in vec])


def _filter_clauses(filters: SearchFilters) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    max_rent = filters.get("max_rent")
    if max_rent is not None:
        clauses.append("p.rent <= %s")
        params.append(int(max_rent))

    layout = filters.get("layout")
    if layout:
        clauses.append("p.layout = %s")
        params.append(str(layout))

    max_walk_min = filters.get("max_walk_min")
    if max_walk_min is not None:
        clauses.append("p.walk_min <= %s")
        params.append(int(max_walk_min))

    pet_ok = filters.get("pet_ok")
    if pet_ok is not None:
        clauses.append("p.pet_ok = %s")
        params.append(bool(pet_ok))

    max_age = filters.get("max_age")
    if max_age is not None:
        clauses.append("p.age_years <= %s")
        params.append(int(max_age))

    return clauses, params
