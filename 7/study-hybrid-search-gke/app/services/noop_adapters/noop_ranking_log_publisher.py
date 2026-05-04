"""Null ``RankingLogPublisher`` — discards every call.

Selected when ``RANKING_LOG_TOPIC`` is empty (e.g. local dev without
Pub/Sub). Search continues to work; offline evaluation simply has no
data for those requests.
"""

from __future__ import annotations

from app.domain.candidate import Candidate
from app.services.protocols.ranking_log_publisher import RankingLogPublisher


class NoopRankingLogPublisher(RankingLogPublisher):
    def publish_candidates(
        self,
        *,
        request_id: str,
        candidates: list[Candidate],
        final_ranks: list[int],
        scores: list[float | None],
        model_path: str | None,
    ) -> None:
        return None
