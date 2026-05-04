"""In-memory ``RankingLogPublisher`` collecting calls for assertions."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.candidate import Candidate
from app.services.protocols.ranking_log_publisher import RankingLogPublisher


@dataclass(frozen=True)
class RankingLogCall:
    request_id: str
    candidates: tuple[Candidate, ...]
    final_ranks: tuple[int, ...]
    scores: tuple[float | None, ...]
    model_path: str | None


class InMemoryRankingLogPublisher(RankingLogPublisher):
    def __init__(self) -> None:
        self.calls: list[RankingLogCall] = []

    def publish_candidates(
        self,
        *,
        request_id: str,
        candidates: list[Candidate],
        final_ranks: list[int],
        scores: list[float | None],
        model_path: str | None,
    ) -> None:
        self.calls.append(
            RankingLogCall(
                request_id=request_id,
                candidates=tuple(candidates),
                final_ranks=tuple(final_ranks),
                scores=tuple(scores),
                model_path=model_path,
            )
        )
