"""Null ``FeedbackRecorder`` — discards feedback events.

Selected when ``FEEDBACK_TOPIC`` is empty. /feedback endpoint still
returns ``accepted=true`` because the ingest path is intentionally
best-effort (telemetry, not transactional).
"""

from __future__ import annotations

from app.services.protocols.feedback_recorder import FeedbackRecorder


class NoopFeedbackRecorder(FeedbackRecorder):
    def record(self, *, request_id: str, property_id: str, action: str) -> None:
        return None
