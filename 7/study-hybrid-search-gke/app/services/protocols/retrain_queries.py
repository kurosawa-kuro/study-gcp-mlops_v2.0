"""Port for retrain-decision query surface.

Concrete adapter: :class:`app.services.adapters.retrain.BigQueryRetrainQueries`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class RetrainQueries(Protocol):
    def last_run_finished_at(self) -> datetime | None: ...
    def feedback_rows_since(self, since: datetime) -> int | None: ...
    def ndcg_in_window(self, *, start: datetime, end: datetime) -> float | None: ...
