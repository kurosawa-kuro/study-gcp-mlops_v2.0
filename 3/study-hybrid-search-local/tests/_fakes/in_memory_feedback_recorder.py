"""In-memory ``FeedbackRecorder`` capturing events for assertions."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.protocols.feedback_recorder import FeedbackRecorder


@dataclass(frozen=True)
class FeedbackEvent:
    request_id: str
    property_id: str
    action: str


class InMemoryFeedbackRecorder(FeedbackRecorder):
    def __init__(self, *, fail: bool = False) -> None:
        self.events: list[FeedbackEvent] = []
        self._fail = fail

    def record(self, *, request_id: str, property_id: str, action: str) -> None:
        if self._fail:
            raise RuntimeError("InMemoryFeedbackRecorder configured to raise")
        self.events.append(
            FeedbackEvent(
                request_id=request_id,
                property_id=property_id,
                action=action,
            )
        )
