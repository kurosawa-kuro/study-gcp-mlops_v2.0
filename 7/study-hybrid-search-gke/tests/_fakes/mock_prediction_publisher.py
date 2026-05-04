"""Recorded-call ``PredictionPublisher`` stub."""

from __future__ import annotations

from app.services.protocols.publisher import PredictionPublisher


class MockPredictionPublisher(PredictionPublisher):
    def __init__(self, *, fail: bool = False) -> None:
        self.payloads: list[dict[str, object]] = []
        self._fail = fail

    def publish(self, payload: dict[str, object]) -> None:
        if self._fail:
            raise RuntimeError("MockPredictionPublisher configured to raise")
        self.payloads.append(dict(payload))
