"""``FeedbackService`` — /feedback orchestration.

Thin wrapper around :class:`FeedbackRecorder` that swallows transient
publish failures (telemetry, not transactional). The HTTP handler maps
the boolean to ``accepted`` in the response.
"""

from __future__ import annotations

from app.services.protocols.feedback_recorder import FeedbackRecorder
from ml.common.logging import get_logger

logger = get_logger("app.feedback_service")


class FeedbackService:
    def __init__(self, *, recorder: FeedbackRecorder) -> None:
        self._recorder = recorder

    def record(self, *, request_id: str, property_id: str, action: str) -> bool:
        """Returns ``True`` on successful publish, ``False`` on transient failure."""
        try:
            self._recorder.record(
                request_id=request_id,
                property_id=property_id,
                action=action,
            )
        except Exception:
            logger.exception("Feedback publish failed — continuing")
            return False
        return True
