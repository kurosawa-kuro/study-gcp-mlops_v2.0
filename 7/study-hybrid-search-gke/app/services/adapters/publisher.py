"""Concrete adapter implementing :class:`app.publisher.PredictionPublisher` over Pub/Sub."""

from __future__ import annotations

import json

from app.services.adapters.internal.pubsub_diagnostics import (
    log_publish_failure,
    logger,
    runtime_sa_hint,
)


class PubSubPublisher:
    """Synchronously publishes JSON-encoded payloads to a Pub/Sub topic."""

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

    def publish(self, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self._client.publish(self._topic_path, data).result(timeout=5)
        except Exception as exc:
            log_publish_failure(
                where="PubSubPublisher.publish",
                topic_path=self._topic_path,
                exc=exc,
            )
            raise
