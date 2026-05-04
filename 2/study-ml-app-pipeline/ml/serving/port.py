"""Predictor inbound-facing port."""

from typing import Protocol


class Predictor(Protocol):
    def predict(self, values: dict) -> float: ...
