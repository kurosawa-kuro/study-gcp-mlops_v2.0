"""Phase 3 — PostgreSQL ``feedback_events`` recorder.

Phase 7 の ``PubSubFeedbackRecorder`` を PostgreSQL 直接 INSERT に差し替えた版。
``UNIQUE (request_id, property_id, action)`` の冪等性は 0001_init.sql で担保済。
"""

from __future__ import annotations

import psycopg

from app.services.protocols.feedback_recorder import FeedbackRecorder
from ml.common import get_logger


class PostgresFeedbackRecorder(FeedbackRecorder):
    def __init__(self, *, dsn: str, table: str = "feedback_events") -> None:
        self._dsn = dsn
        self._table = table
        self._logger = get_logger("app.adapters.postgres_feedback_recorder")

    def record(self, *, request_id: str, property_id: str, action: str) -> None:
        sql = (
            f"INSERT INTO {self._table} (request_id, property_id, action) "
            "VALUES (%s, %s, %s) ON CONFLICT (request_id, property_id, action) DO NOTHING"
        )
        try:
            with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
                cur.execute(sql, [request_id, property_id, action])
                conn.commit()
        except Exception:
            self._logger.exception(
                "feedback INSERT failed (request_id=%s property_id=%s action=%s)",
                request_id,
                property_id,
                action,
            )
            raise
