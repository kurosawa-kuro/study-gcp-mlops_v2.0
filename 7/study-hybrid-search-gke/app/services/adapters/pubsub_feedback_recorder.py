"""``FeedbackRecorder`` adapter — Pub/Sub on the ``search-feedback`` topic."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.services.adapters.internal.pubsub_diagnostics import (
    log_publish_failure,
    logger,
    runtime_sa_hint,
)


class PubSubFeedbackRecorder:
    """Writes feedback events to the ``search-feedback`` Pub/Sub topic."""

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

    def record(self, *, request_id: str, property_id: str, action: str) -> None:
        payload = {
            "request_id": request_id,
            "property_id": property_id,
            "action": action,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self._client.publish(self._topic_path, data).result(timeout=5)
        except Exception as exc:
            log_publish_failure(
                where="PubSubFeedbackRecorder.record",
                topic_path=self._topic_path,
                exc=exc,
            )
            raise
