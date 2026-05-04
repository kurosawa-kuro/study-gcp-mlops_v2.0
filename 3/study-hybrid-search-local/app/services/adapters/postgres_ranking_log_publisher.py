"""Phase 3 — PostgreSQL ``ranking_log`` publisher.

Phase 7 の ``PubSubRankingLogPublisher`` を PostgreSQL 直接 INSERT に差し替えた版。
Phase 4 で Pub/Sub → BigQuery sink に再差し替え可能。

failure semantics: best-effort。SearchService 側で `_safe_publish_candidates` が
exception を握り潰すので、ここでは raise しても /search 自体は壊れない。
"""

from __future__ import annotations

import json

import psycopg

from app.domain.candidate import Candidate
from app.services.protocols.ranking_log_publisher import RankingLogPublisher
from ml.common import get_logger


class PostgresRankingLogPublisher(RankingLogPublisher):
    def __init__(self, *, dsn: str, table: str = "ranking_log") -> None:
        self._dsn = dsn
        self._table = table
        self._logger = get_logger("app.adapters.postgres_ranking_log")

    def publish_candidates(
        self,
        *,
        request_id: str,
        candidates: list[Candidate],
        final_ranks: list[int],
        scores: list[float | None],
        model_path: str | None,
    ) -> None:
        if not candidates:
            return

        sql = (
            f"INSERT INTO {self._table} "
            "(request_id, property_id, lexical_rank, semantic_rank, me5_score, "
            "final_rank, score, model_path, property_features) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)"
        )
        rows = []
        for i, cand in enumerate(candidates):
            score = scores[i]
            rows.append(
                (
                    request_id,
                    cand.property_id,
                    int(cand.lexical_rank) if cand.lexical_rank else None,
                    int(cand.semantic_rank) if cand.semantic_rank else None,
                    float(cand.me5_score),
                    int(final_ranks[i]),
                    float(score) if score is not None else None,
                    model_path,
                    json.dumps(cand.property_features, ensure_ascii=False),
                )
            )

        try:
            with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
                cur.executemany(sql, rows)
                conn.commit()
        except Exception:
            self._logger.exception(
                "log_publish_failure: ranking_log INSERT failed for request_id=%s "
                "(candidates=%d). Continuing without persistence.",
                request_id,
                len(candidates),
            )
