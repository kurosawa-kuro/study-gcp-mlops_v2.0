"""Opt-in **full recreate** gate: destroy-all → deploy-all → same acceptance checks.

**Unstable by design** after ``destroy-all``: Vertex Feature Group / Feature
Online Store names can remain in GCP async-delete for many minutes; immediate
``deploy-all`` may hit HTTP **409** (same symptom as 2026-05-03 session). This
gate validates **end-to-end recreate when GCP timing allows** — not the same
contract as ``test_phase7_acceptance_gate`` (existing env).

Prefer ``deploy-all`` alone after a wait, or acceptance-on-existing-env, for
routine V6 verification.

Run (long-running; tee + monitor):

    cd 7/study-hybrid-search-gke
    RUN_LIVE_GCP_FULL_RECREATE=1 uv run pytest tests/e2e/test_phase7_full_recreate_gate.py -m 'live_gcp and full_recreate' -v 2>&1 | tee _full_recreate_gate.log

Monitor (another terminal):

    tail -f /home/ubuntu/repos/study-gcp-mlops/7/study-hybrid-search-gke/_full_recreate_gate.log
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.e2e.phase7_acceptance_checks import run_phase7_live_acceptance_checks

pytestmark = [pytest.mark.live_gcp, pytest.mark.full_recreate]

REPO_ROOT = Path(__file__).resolve().parents[2]


def _require_full_recreate() -> None:
    if os.environ.get("RUN_LIVE_GCP_FULL_RECREATE", "").strip() != "1":
        pytest.skip(
            "set RUN_LIVE_GCP_FULL_RECREATE=1 for destroy-all -> deploy-all gate "
            "(destructive; see module docstring)"
        )


def _run(cmd: list[str], *, timeout: int) -> None:
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        tail = "\n".join(out.splitlines()[-40:])
        raise AssertionError(f"command failed rc={proc.returncode}: {' '.join(cmd)}\n{tail}")


def test_phase7_full_recreate_acceptance_live() -> None:
    _require_full_recreate()
    _run(["make", "destroy-all"], timeout=1800)
    _run(["make", "deploy-all"], timeout=3600)
    run_phase7_live_acceptance_checks(REPO_ROOT)
