"""Phase 7 workflow contract — gcloud Composer stdout → JSON array.

Incident (2026-05): ``gcloud composer environments run`` mixes log lines and
``Executing the command: [ airflow ... ]`` before the real payload. A naive
``json.loads(stdout)`` fails. Real Airflow JSON starts at ``[{`` — pinned by
:func:`scripts.ops.composer_task_states.extract_json_array`.
"""

from __future__ import annotations

import json

import pytest

from scripts.ops import composer_task_states as cts


def test_extract_json_array_skips_executing_command_prologue() -> None:
    """First ``[`` belongs to gcloud banner; task JSON is ``[{`` onward."""
    messy = """Executing the command: [ airflow tasks states-for-dag-run -o json \\
      mydag manual__2026-05-03T09:18:07+00:00 ]...
Loaded credentials...
[{"task_id": "check_retrain", "state": "success"}, {"task_id": "submit_train_pipeline", "state": "running"}]
"""
    raw = cts.extract_json_array(messy)
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["task_id"] == "check_retrain"


def test_extract_json_array_prefers_array_of_objects_over_inner_brackets() -> None:
    """Regression: must not stop at the airflow CLI ``[ ... ]`` bracket group."""
    prologue = "Executing the command: [ airflow dags trigger x ]\n"
    payload = '[{"task_id": "a", "state": null}]'
    raw = cts.extract_json_array(prologue + payload)
    assert json.loads(raw)[0]["task_id"] == "a"


def test_extract_json_array_handles_empty_array() -> None:
    text = "noise\n[]\ntrailing"
    raw = cts.extract_json_array(text)
    assert raw.strip() == "[]"


def test_latest_run_id_from_list_runs_finds_manual_run_id() -> None:
    """Best-effort parse used by ``--latest`` must survive ASCII table noise."""
    table = """
| dag_id              | dag_run_id                          | state |
| retrain_orchestration | manual__2026-05-03T09:18:07+00:00 | running |
"""
    assert cts._latest_run_id_from_list_runs(table) == "manual__2026-05-03T09:18:07+00:00"


def test_balanced_array_respects_string_literals_with_brackets() -> None:
    """Brackets inside JSON strings must not truncate early."""
    text = """x
[{"note": "a]b]", "task_id": "t", "state": "success"}]
"""
    raw = cts.extract_json_array(text)
    row = json.loads(raw)[0]
    assert row["note"] == "a]b]"


def test_extract_json_array_missing_array_raises() -> None:
    with pytest.raises(ValueError, match="no JSON array"):
        cts.extract_json_array("no brackets here")
