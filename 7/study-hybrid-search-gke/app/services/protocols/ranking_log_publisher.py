"""``RankingLogPublisher`` Port — per-request ranking log emission.

Implementations: ``PubSubRankingLogPublisher`` (publishes to ``ranking-log``
topic; consumed by Dataflow → ``ranking_log`` BigQuery table for offline
evaluation and ranker retraining), ``NoopRankingLogPublisher`` (disabled
when ``RANKING_LOG_TOPIC`` is empty).

Each ``publish_candidates`` call corresponds to one /search invocation
and emits one row per **retrieved** candidate (not just the top-K
returned to the user) so downstream ranker retraining sees the full pool.

Failure semantics: emission is best-effort; failures are logged but do
not fail the /search response. Strict delivery guarantees are out of
scope (offline evaluation tolerates gaps).
"""

from __future__ import annotations

from typing import Protocol

from app.domain.candidate import Candidate


class RankingLogPublisher(Protocol):
    """Writes one row per (request_id, property_id) candidate to the ranking log.

    ``scores`` is ``[None, None, ...]`` in Phase 4 fallback mode (no booster);
    in Phase 6 rerank mode each entry matches the candidate by index.

    ``model_path`` is the reranker model artifact URI (Vertex Model Registry
    alias resolution result). ``None`` in fallback mode so offline
    evaluation can distinguish reranked vs. baseline rows.
    """

    def publish_candidates(
        self,
        *,
        request_id: str,
        candidates: list[Candidate],
        final_ranks: list[int],
        scores: list[float | None],
        model_path: str | None,
    ) -> None: ...
