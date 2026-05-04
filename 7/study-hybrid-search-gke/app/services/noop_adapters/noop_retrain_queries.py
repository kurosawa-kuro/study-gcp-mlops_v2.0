"""Null ``RetrainQueries`` for startup paths that must avoid BigQuery."""

from __future__ import annotations

from datetime import datetime

from app.services.protocols.retrain_queries import RetrainQueries


class NoopRetrainQueries(RetrainQueries):
    def last_run_finished_at(self) -> datetime | None:
        return None

    def feedback_rows_since(self, since: datetime) -> int | None:
        return None

    def ndcg_in_window(self, *, start: datetime, end: datetime) -> float | None:
        return None
