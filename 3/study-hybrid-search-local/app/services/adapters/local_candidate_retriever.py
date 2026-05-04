"""Phase 3 — Local CandidateRetriever (lexical + semantic + RRF fusion + DB enrich).

Phase 7 の ``BigQueryCandidateRetriever`` 相当。違いは:
- lexical 経路は ``LexicalSearchPort`` (Meilisearch) を呼ぶ
- semantic 経路は ``SemanticSearchPort`` (pgvector) を呼ぶ
- RRF 融合は ``app.services.ranking.rrf_fuse`` を再利用
- ``Candidate.property_features`` の埋めは PostgreSQL `properties` テーブルから直接 SELECT

Phase 4 で BigQuery candidate retriever (BQ JOIN 1 本で完結) に差し替え可能。
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from app.domain.candidate import Candidate
from app.domain.retrieval import LexicalResult, SemanticResult
from app.domain.search import SearchFilters
from app.services.protocols.candidate_retriever import CandidateRetriever
from app.services.protocols.lexical_search import LexicalSearchPort
from app.services.protocols.semantic_search import SemanticSearchPort
from app.services.ranking import rrf_fuse
from ml.common import get_logger


class LocalCandidateRetriever(CandidateRetriever):
    def __init__(
        self,
        *,
        lexical_search: LexicalSearchPort,
        semantic_search: SemanticSearchPort,
        dsn: str,
        rrf_k: int = 60,
        candidate_pool_size: int = 100,
    ) -> None:
        self._lexical = lexical_search
        self._semantic = semantic_search
        self._dsn = dsn
        self._rrf_k = rrf_k
        self._pool_size = candidate_pool_size
        self._logger = get_logger("app.adapters.local_candidate_retriever")

    def retrieve(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        filters: SearchFilters,
        top_k: int,
    ) -> list[Candidate]:
        # 1. lexical / semantic を独立に取得
        lex: list[LexicalResult] = self._lexical.search(
            query=query_text,
            filters=filters,
            top_k=self._pool_size,
        )
        sem: list[SemanticResult] = self._semantic.search(
            query_vector=query_vector,
            filters=filters,
            top_k=self._pool_size,
        )
        if not lex and not sem:
            return []

        # 2. RRF 融合 → top_k に絞る
        fused_ids = rrf_fuse(
            lexical_results=[(r.property_id, r.rank) for r in lex],
            semantic_results=[(r.property_id, r.rank) for r in sem],
            top_n=top_k,
            k=self._rrf_k,
        )
        if not fused_ids:
            return []

        # 3. lexical / semantic / similarity を index 化
        lex_by_id: dict[str, int] = {r.property_id: r.rank for r in lex}
        sem_by_id: dict[str, int] = {r.property_id: r.rank for r in sem}
        sim_by_id: dict[str, float] = {r.property_id: r.similarity for r in sem}

        # 4. PostgreSQL から property の表示用メタ + ranker 補助特徴量を引く
        property_features = self._fetch_property_features(fused_ids)

        # 5. Candidate 組み立て
        out: list[Candidate] = []
        for property_id in fused_ids:
            features = property_features.get(property_id, {})
            out.append(
                Candidate(
                    property_id=property_id,
                    lexical_rank=lex_by_id.get(property_id, 0),
                    semantic_rank=sem_by_id.get(property_id, 0),
                    me5_score=float(sim_by_id.get(property_id, 0.0)),
                    property_features=features,
                )
            )
        return out

    def _fetch_property_features(
        self,
        property_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not property_ids:
            return {}
        sql = """
            SELECT
                p.property_id, p.title, p.city, p.ward, p.layout,
                p.rent, p.walk_min, p.age_years, p.area_m2, p.pet_ok,
                fm.ctr, fm.fav_rate, fm.inquiry_rate
            FROM properties AS p
            LEFT JOIN feature_mart_property_features_daily AS fm
                ON fm.property_id = p.property_id
            WHERE p.property_id = ANY(%s)
        """
        out: dict[str, dict[str, Any]] = {}
        try:
            with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
                cur.execute(sql, [property_ids])
                cols = [desc[0] for desc in cur.description] if cur.description else []
                for row in cur.fetchall():
                    record = dict(zip(cols, row, strict=True))
                    pid = str(record.pop("property_id"))
                    out[pid] = record
        except Exception:
            self._logger.exception("LocalCandidateRetriever._fetch_property_features failed")
            return {pid: {} for pid in property_ids}
        # JOIN で抜けたものは {} で埋める。
        for pid in property_ids:
            out.setdefault(pid, {})
        return out


# property_features の JSON 化が必要な caller がいる場合の helper (現状は dict 直接利用)。
def encode_property_features(features: dict[str, Any]) -> str:
    return json.dumps(features, ensure_ascii=False)
