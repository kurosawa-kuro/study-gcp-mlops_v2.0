"""Real-time deploy monitor for in-progress deploy-all (Phase 7 port).

Usage:
  make ops-deploy-monitor
  uv run python -m scripts.deploy.monitor

Behavior:
1) Starts deploy-all as a child process (unbuffered output).
2) Streams logs in real time and extracts current step context.
3) During Cloud Build wait, periodically prints build status/log URL.
4) Detects long silent periods and reports where deployment is stuck.
5) On failure, prints likely timeout root cause with step/build context.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from scripts._common import env, fail, run


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor deploy-all in real time.")
    parser.add_argument(
        "--poll-sec",
        type=int,
        default=8,
        help="Polling interval for progress heartbeat (default: 8)",
    )
    parser.add_argument(
        "--stall-warn-sec",
        type=int,
        default=120,
        help="Warn when no new log line is seen for this many seconds (default: 120)",
    )
    parser.add_argument(
        "--quiet-steps",
        action="store_true",
        help="Do not print every raw line; print only heartbeat/summary logs",
    )
    return parser.parse_args(argv)


def _build_describe(project_id: str, build_id: str) -> tuple[str, str]:
    proc = run(
        [
            "gcloud",
            "builds",
            "describe",
            build_id,
            f"--project={project_id}",
            "--format=json",
        ],
        capture=True,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return "", ""
    status = str(payload.get("status") or "")
    log_url = str(payload.get("logUrl") or "")
    return status, log_url


_STEP_RE = re.compile(r"deploy-all\s+step\s+(\d+)/(\d+):\s+(.+)$")
_BUILD_WAIT_RE = re.compile(r"Cloud Build wait id=([a-z0-9-]+)\s+timeout=(\d+)s")


@dataclass
class MonitorState:
    current_step_no: int = 0
    current_step_total: int = 0
    current_step_label: str = "not-started"
    current_build_id: str = ""
    current_build_timeout_sec: int = 0
    current_build_started_at: float = 0.0
    last_line_at: float = 0.0
    last_line: str = ""


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _maybe_parse_step(line: str, state: MonitorState) -> None:
    m = _STEP_RE.search(line)
    if not m:
        return
    state.current_step_no = int(m.group(1))
    state.current_step_total = int(m.group(2))
    state.current_step_label = m.group(3).strip()
    state.current_build_id = ""
    state.current_build_timeout_sec = 0
    state.current_build_started_at = 0.0
    print(
        f"[monitor] step-enter step={state.current_step_no}/{state.current_step_total} "
        f"label={state.current_step_label}"
    )


def _maybe_parse_build_wait(line: str, state: MonitorState, now_ts: float) -> None:
    m = _BUILD_WAIT_RE.search(line)
    if not m:
        return
    state.current_build_id = m.group(1)
    state.current_build_timeout_sec = int(m.group(2))
    state.current_build_started_at = now_ts
    print(
        f"[monitor] build-wait-start build_id={state.current_build_id} "
        f"timeout_sec={state.current_build_timeout_sec} step={state.current_step_no}"
    )


def _print_heartbeat(
    state: MonitorState, project_id: str, now_ts: float, stall_warn_sec: int
) -> None:
    idle_sec = int(max(0, now_ts - state.last_line_at))
    base = (
        f"[monitor] heartbeat t={_now_utc()} step={state.current_step_no}/{state.current_step_total} "
        f"label={state.current_step_label} idle_sec={idle_sec}"
    )

    if state.current_build_id:
        status, log_url = _build_describe(project_id, state.current_build_id)
        elapsed = int(max(0, now_ts - state.current_build_started_at))
        timeout_sec = state.current_build_timeout_sec
        remaining = max(0, timeout_sec - elapsed) if timeout_sec else -1
        print(
            f"{base} build_id={state.current_build_id} build_status={status} "
            f"build_elapsed_sec={elapsed} build_remaining_sec={remaining}"
        )
        if log_url:
            print(f"[monitor] build-log-url {log_url}")
    else:
        print(base)

    if idle_sec >= stall_warn_sec:
        print(
            "[monitor] stall-warning "
            f"no-new-log-for={idle_sec}s current_step={state.current_step_no} "
            f"last_line={state.last_line}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    project_id = env("PROJECT_ID")
    state = MonitorState()
    now = time.monotonic()
    state.last_line_at = now
    state.current_step_label = "launching"

    child_env = dict(os.environ)
    child_env["PYTHONUNBUFFERED"] = "1"
    cmd = ["uv", "run", "python", "-u", "-m", "scripts.setup.deploy_all"]
    print(f"[monitor] start deploy-all command={' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=child_env,
    )

    assert proc.stdout is not None
    next_heartbeat = time.monotonic() + max(1, args.poll_sec)
    poll_interval = min(max(1, args.poll_sec), 2)
    while True:
        now_ts = time.monotonic()
        ready, _, _ = select.select([proc.stdout], [], [], poll_interval)
        if ready:
            line = proc.stdout.readline()
            if line:
                stripped = line.rstrip("\n")
                state.last_line = stripped
                state.last_line_at = now_ts
                _maybe_parse_step(stripped, state)
                _maybe_parse_build_wait(stripped, state, now_ts)
                if not args.quiet_steps:
                    print(stripped)
            elif proc.poll() is not None:
                break
        elif proc.poll() is not None:
            break

        if now_ts >= next_heartbeat:
            _print_heartbeat(state, project_id, now_ts, args.stall_warn_sec)
            next_heartbeat = now_ts + max(1, args.poll_sec)

    rc = proc.wait()
    if rc == 0:
        print(
            "[monitor] deploy-all succeeded "
            f"final_step={state.current_step_no}/{state.current_step_total} "
            f"label={state.current_step_label}"
        )
        return 0

    failure_reason = "deploy-all returned non-zero"
    if state.current_build_id:
        status, log_url = _build_describe(project_id, state.current_build_id)
        if status in {"WORKING", "QUEUED"}:
            failure_reason = (
                "deploy-all failed during cloud-build wait "
                f"(build_id={state.current_build_id}, status={status}, step={state.current_step_no})"
            )
        else:
            failure_reason = (
                "deploy-all failed after cloud-build completed "
                f"(build_id={state.current_build_id}, status={status}, step={state.current_step_no}, "
                f"last_line={state.last_line})"
            )
        if log_url:
            print(f"[monitor] failure-build-log-url {log_url}")
        if status == "TIMEOUT":
            failure_reason += " timeout detected in Cloud Build"
    elif state.current_step_no > 0:
        failure_reason = (
            f"deploy-all failed at step {state.current_step_no}/{state.current_step_total} "
            f"({state.current_step_label})"
        )
    return fail(f"[monitor] {failure_reason}")


if __name__ == "__main__":
    raise SystemExit(main())
