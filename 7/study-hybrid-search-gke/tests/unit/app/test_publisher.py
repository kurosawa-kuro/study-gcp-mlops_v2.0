"""Tests for the publisher port + null implementation.

The concrete Pub/Sub adapter is covered by ``test_adapters.py``.
"""

from __future__ import annotations

from app.services.protocols.publisher import NoopPublisher


def test_noop_publisher_accepts_any_payload() -> None:
    p = NoopPublisher()
    p.publish({"anything": 1, "nested": {"a": "b"}})  # no-op, must not raise
