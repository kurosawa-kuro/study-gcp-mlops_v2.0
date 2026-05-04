"""Unit tests for scripts.ops.composer_task_states JSON extraction."""

from __future__ import annotations

from scripts.ops.composer_task_states import _latest_run_id_from_list_runs, extract_json_array


def test_extract_json_array_strips_prologue() -> None:
    blob = """Executing the command: [ airflow tasks states-for-dag-run -o json foo bar ]
Use ctrl-c to interrupt the command
[{"dag_id": "x", "task_id": "t1", "state": "success"}]
"""
    raw = extract_json_array(blob)
    assert raw.startswith("[")
    assert '"task_id": "t1"' in raw


def test_latest_run_id_first_row() -> None:
    table = """
dag_id | run_id | state
retrain_orchestration | manual__2026-05-03T08:23:51+00:00 | running
"""
    assert _latest_run_id_from_list_runs(table) == "manual__2026-05-03T08:23:51+00:00"
