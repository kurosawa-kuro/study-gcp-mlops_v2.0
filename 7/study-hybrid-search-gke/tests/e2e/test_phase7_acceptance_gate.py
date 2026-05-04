"""Opt-in live acceptance on an **already deployed** environment.

This is the canonical **V6** gate: ConfigMap + ``ops-search-components`` + VVS +
Feature Group + feedback / ranking / accuracy — **without** tearing down infra
inside the test.

Destructive ``destroy-all -> deploy-all`` PDCA is a separate unstable gate; see
``test_phase7_full_recreate_gate.py``.

Run (dev project only, kubectl context ready):

    RUN_LIVE_GCP_ACCEPTANCE=1 pytest tests/e2e/test_phase7_acceptance_gate.py -m live_gcp
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.e2e.phase7_acceptance_checks import run_phase7_live_acceptance_checks

pytestmark = pytest.mark.live_gcp

REPO_ROOT = Path(__file__).resolve().parents[2]


def _require_acceptance_env() -> None:
    if os.environ.get("RUN_LIVE_GCP_ACCEPTANCE", "").strip() != "1":
        pytest.skip("set RUN_LIVE_GCP_ACCEPTANCE=1 to run live acceptance on existing deploy")


def test_phase7_live_acceptance_on_existing_env() -> None:
    """Requires prior ``make deploy-all`` (or equivalent)."""
    _require_acceptance_env()
    run_phase7_live_acceptance_checks(REPO_ROOT)
