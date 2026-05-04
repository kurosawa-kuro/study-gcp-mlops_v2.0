"""Publisher Port + in-process null implementation.

The concrete Pub/Sub adapter (:class:`app.services.adapters.PubSubPublisher`) lives in
:mod:`app.services.adapters.publisher`; composition is done by :mod:`app.main` (lifespan).
"""

from __future__ import annotations

from typing import Protocol


class PredictionPublisher(Protocol):
    def publish(self, payload: dict[str, object]) -> None: ...


class NoopPublisher:
    def publish(self, payload: dict[str, object]) -> None:
        pass
