"""Port for property popularity scoring (Phase 6 T1 — BQML).

Returns a dict ``{property_id: score}`` for the requested IDs. Missing IDs
should be absent from the returned dict so callers distinguish "unknown"
from "zero popularity". Implementations are free to batch-predict for
throughput (the Phase 5 BigQuery client auto-batches via ``ML.PREDICT``).
"""

from __future__ import annotations

from typing import Protocol


class PopularityScorer(Protocol):
    def score(self, property_ids: list[str]) -> dict[str, float]: ...
