"""Pin the Observability seam contract.

``Container.observability`` is the canonical place to wire metrics +
logging (and future tracing). These tests keep the two factories
(``from_env`` / ``for_test``) and the SLO-label contract in place so a
future refactor cannot regress the seam.
"""

from __future__ import annotations

import logging

import pytest

from app.observability import Observability


def test_for_test_uses_stdlib_logger_and_default_service() -> None:
    """``for_test`` must NOT depend on env / cloud-logging config."""
    obs = Observability.for_test()
    assert obs.service_name == "search-api-test"
    logger = obs.get_logger("dummy")
    # Stdlib ``logging.getLogger`` returns Logger or PlaceHolder; the
    # project-wide ``ml.common.logging.get_logger`` would attach Cloud
    # Logging handlers — we want a plain stdlib logger here.
    assert isinstance(logger, logging.Logger)


def test_for_test_accepts_custom_service_name() -> None:
    obs = Observability.for_test(service_name="my-service")
    assert obs.service_name == "my-service"


def test_from_env_reads_otel_service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """``from_env`` honours ``OTEL_SERVICE_NAME``; falls back to ``search-api``.

    The fallback value is the SLO module's filter contract — see
    ``infra/terraform/modules/slo/main.tf`` good/total filter.
    """
    monkeypatch.setenv("OTEL_SERVICE_NAME", "search-api-canary")
    obs = Observability.from_env()
    assert obs.service_name == "search-api-canary"


def test_from_env_default_matches_slo_label_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    obs = Observability.from_env()
    # Pinned: this is the literal value the SLO module filters on.
    # If it ever drifts, GMP scrape selects zero series and Terraform
    # apply for ``module.slo`` fails.
    assert obs.service_name == "search-api"
