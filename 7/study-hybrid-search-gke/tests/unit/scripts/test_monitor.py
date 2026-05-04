"""Unit tests for scripts.deploy.monitor — log parsing + state transitions.

The monitor's value is detecting *where* deploy-all is stuck. That detection
hinges on two regex parsers (``_STEP_RE`` / ``_BUILD_WAIT_RE``) and the
``MonitorState`` machine they feed. These tests pin both so refactoring the
monitor doesn't silently break stall detection in the next Phase 7 rollout.
"""

from __future__ import annotations

from scripts.deploy.monitor import (
    _BUILD_WAIT_RE,
    _STEP_RE,
    MonitorState,
    _maybe_parse_build_wait,
    _maybe_parse_step,
)


def test_step_regex_matches_deploy_all_step_log_format() -> None:
    """deploy_all.py emits lines like `deploy-all  step 3/6: label` (two
    spaces between "deploy-all" and "step"). The regex must tolerate variable
    whitespace so format tweaks in deploy_all.py don't silently break monitor.
    """
    line = " deploy-all  step 3/6: apply Terraform"
    m = _STEP_RE.search(line)
    assert m is not None
    assert m.group(1) == "3"
    assert m.group(2) == "6"
    assert m.group(3) == "apply Terraform"


def test_step_regex_matches_single_space() -> None:
    line = "deploy-all step 1/7: tf-bootstrap"
    m = _STEP_RE.search(line)
    assert m is not None
    assert m.groups() == ("1", "7", "tf-bootstrap")


def test_step_regex_ignores_unrelated_lines() -> None:
    for line in (
        "[info] nothing to see here",
        "deploy-all DONE",
        "step 1/2 something",  # missing "deploy-all" prefix
    ):
        assert _STEP_RE.search(line) is None


def test_build_wait_regex_extracts_build_id_and_timeout() -> None:
    line = "[3/4] Cloud Build wait id=abc-123-def timeout=1800s"
    m = _BUILD_WAIT_RE.search(line)
    assert m is not None
    assert m.group(1) == "abc-123-def"
    assert m.group(2) == "1800"


def test_build_wait_regex_requires_numeric_timeout() -> None:
    # Missing timeout value → no match (monitor would not start build tracking)
    assert _BUILD_WAIT_RE.search("Cloud Build wait id=xyz timeout=") is None


def test_maybe_parse_step_updates_state_and_clears_build_tracking() -> None:
    """When a new step begins, any in-progress build tracking must reset so
    the heartbeat doesn't keep polling a stale build_id from the previous step.
    """
    state = MonitorState()
    state.current_build_id = "stale-build"
    state.current_build_timeout_sec = 1200
    state.current_build_started_at = 42.0

    _maybe_parse_step("deploy-all  step 5/7: kubectl set image", state)

    assert state.current_step_no == 5
    assert state.current_step_total == 7
    assert state.current_step_label == "kubectl set image"
    assert state.current_build_id == ""  # cleared
    assert state.current_build_timeout_sec == 0
    assert state.current_build_started_at == 0.0


def test_maybe_parse_step_noop_for_unrelated_line() -> None:
    state = MonitorState()
    state.current_step_label = "launching"
    _maybe_parse_step("[info] unrelated diagnostic", state)
    assert state.current_step_no == 0
    assert state.current_step_label == "launching"


def test_maybe_parse_build_wait_records_build_id_and_start_time() -> None:
    state = MonitorState()
    _maybe_parse_build_wait(
        "[3/4] Cloud Build wait id=build-xyz timeout=1800s",
        state,
        now_ts=1000.0,
    )
    assert state.current_build_id == "build-xyz"
    assert state.current_build_timeout_sec == 1800
    assert state.current_build_started_at == 1000.0


def test_maybe_parse_build_wait_noop_for_unrelated_line() -> None:
    state = MonitorState()
    _maybe_parse_build_wait("[info] some other log", state, now_ts=1000.0)
    assert state.current_build_id == ""
    assert state.current_build_timeout_sec == 0
