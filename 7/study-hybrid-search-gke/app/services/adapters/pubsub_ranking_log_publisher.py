"""``RankingLogPublisher`` adapter — Pub/Sub on the ``ranking-log`` topic.

One row per (request_id, property_id) candidate (not just top-K) so
downstream Dataflow / BigQuery / ranker retraining sees the full pool.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.domain.candidate import Candidate
from app.services.adapters.internal.pubsub_diagnostics import (
    as_float,
    log_publish_failure,
    logger,
    runtime_sa_hint,
)


class PubSubRankingLogPublisher:
    """Writes ranking-log rows to the ``ranking-log`` Pub/Sub topic."""

    def __init__(self, *, project_id: str, topic: str) -> None:
        from google.cloud import pubsub_v1  # type: ignore[attr-defined]

        self._client = pubsub_v1.PublisherClient()
        self._topic_path = self._client.topic_path(project_id, topic)
        logger.info(
            "pubsub.publisher init class=%s topic_path=%s sa_hint=%s",
            type(self).__name__,
            self._topic_path,
            runtime_sa_hint(),
        )

    def publish_candidates(
        self,
        *,
        request_id: str,
        candidates: list[Candidate],
        final_ranks: list[int],
        scores: list[float | None],
        model_path: str | None,
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        for cand, final_rank, score in zip(candidates, final_ranks, scores, strict=True):
            payload = {
                "request_id": request_id,
                "ts": ts,
                "property_id": cand.property_id,
                "schema_version": 2,
                "lexical_rank": cand.lexical_rank,
                "semantic_rank": cand.semantic_rank,
                "rrf_rank": cand.property_features.get("rrf_rank"),
                "final_rank": final_rank,
                "score": score,
                "me5_score": cand.me5_score,
                "features": {
                    "rent": as_float(cand.property_features.get("rent")),
                    "walk_min": as_float(cand.property_features.get("walk_min")),
                    "age_years": as_float(cand.property_features.get("age_years")),
                    "area_m2": as_float(cand.property_features.get("area_m2")),
                    "ctr": as_float(cand.property_features.get("ctr")),
                    "fav_rate": as_float(cand.property_features.get("fav_rate")),
                    "inquiry_rate": as_float(cand.property_features.get("inquiry_rate")),
                    "me5_score": cand.me5_score,
                    "lexical_rank": float(cand.lexical_rank),
                    "semantic_rank": float(cand.semantic_rank),
                },
                "model_path": model_path,
            }
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                self._client.publish(self._topic_path, data).result(timeout=5)
            except Exception as exc:
                log_publish_failure(
                    where="PubSubRankingLogPublisher.publish_candidates",
                    topic_path=self._topic_path,
                    exc=exc,
                )
                raise
