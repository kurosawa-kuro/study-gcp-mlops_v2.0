"""Programmable ``RetrainQueries`` stub for retrain-policy tests."""

from __future__ import annotations

from datetime import datetime

from app.services.protocols.retrain_queries import RetrainQueries


class StubRetrainQueries(RetrainQueries):
    """Each method returns the configured value verbatim.

    Pass ``ndcg_window_value`` to control ``ndcg_in_window``;
    distinguishing 'current' vs 'prior week' requires a smarter stub
    (override the method) but the constant default fits most cases.
    """

    def __init__(
        self,
        *,
        last_run: datetime | None = None,
        feedback_count: int | None = 0,
        ndcg_window_value: float | None = None,
    ) -> None:
        self._last_run = last_run
        self._feedback_count = feedback_count
        self._ndcg_window_value = ndcg_window_value
        self.feedback_calls: list[datetime] = []
        self.ndcg_calls: list[tuple[datetime, datetime]] = []

    def last_run_finished_at(self) -> datetime | None:
        return self._last_run

    def feedback_rows_since(self, since: datetime) -> int | None:
        self.feedback_calls.append(since)
        return self._feedback_count

    def ndcg_in_window(self, *, start: datetime, end: datetime) -> float | None:
        self.ndcg_calls.append((start, end))
        return self._ndcg_window_value
