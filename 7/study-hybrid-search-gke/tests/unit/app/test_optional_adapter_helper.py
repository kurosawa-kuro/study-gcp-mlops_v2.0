"""Pin the contract of ``resolve_optional_adapter``.

The helper centralises the ``enable_xxx`` guard used by optional
``MlBuilder`` adapters such as ``build_popularity_scorer``. These tests
keep the three observable behaviours in place so a future refactor
cannot silently start raising on disabled flags or swallow the wrong
exception class.
"""

from __future__ import annotations

import logging

import pytest

from app.container.internal.optional_adapter import resolve_optional_adapter


def test_returns_none_when_disabled_without_calling_factory() -> None:
    calls: list[int] = []

    def factory() -> str:
        calls.append(1)
        return "should-not-appear"

    result = resolve_optional_adapter(
        name="x",
        enabled=False,
        factory=factory,
        logger=logging.getLogger("test"),
    )

    assert result is None
    assert calls == [], "factory must not run when enabled=False"


def test_returns_factory_result_when_enabled() -> None:
    sentinel = object()
    result = resolve_optional_adapter(
        name="x",
        enabled=True,
        factory=lambda: sentinel,
        logger=logging.getLogger("test"),
    )
    assert result is sentinel


def test_swallows_factory_exception_and_logs_with_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def factory() -> str:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="test"):
        result = resolve_optional_adapter(
            name="my-adapter",
            enabled=True,
            factory=factory,
            logger=logging.getLogger("test"),
        )

    assert result is None
    assert any("my-adapter" in rec.message for rec in caplog.records), (
        "the failed adapter's name must appear in the log so operators can grep it"
    )
