"""``FeedbackRecorder`` Port — user-feedback ingestion from /feedback.

Implementations: ``PubSubFeedbackRecorder`` (publishes to ``search-feedback``
topic; consumed by Dataflow streaming → BigQuery), ``NoopFeedbackRecorder``
(disabled when ``FEEDBACK_TOPIC`` is empty).

Failure semantics: implementations may raise on transient publish failure;
``/feedback`` handler catches and returns ``accepted=false`` so the user
flow keeps working even when telemetry is degraded.
"""

from __future__ import annotations

from typing import Protocol


class FeedbackRecorder(Protocol):
    """Writes a single feedback event (click / favorite / inquiry) to the log sink.

    ``action`` is one of {"click", "favorite", "inquiry"}; the schema is
    enforced by ``app.schemas.search.FeedbackRequest``. Implementations
    should be idempotent on (request_id, property_id, action) because the
    HTTP client may retry.
    """

    def record(self, *, request_id: str, property_id: str, action: str) -> None: ...
