"""Monitor wrapper for run-all style make targets.

Usage:
  python scripts/local/run_all_monitor.py --log-file logs/run-all.log -- make run-all-core
"""

from __future__ import annotations

import argparse
import os
import select
import subprocess
import time
from datetime import datetime, timezone


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a command with live monitor heartbeats.")
    parser.add_argument(
        "--poll-sec",
        type=int,
        default=8,
        help="Heartbeat interval seconds (default: 8)",
    )
    parser.add_argument(
        "--stall-warn-sec",
        type=int,
        default=120,
        help="Warn when no new output appears for this many seconds (default: 120)",
    )
    parser.add_argument(
        "--log-file",
        required=True,
        help="Path to write full command output log",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to execute, e.g. -- make run-all-core",
    )
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("missing command after --")
    return args


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    os.makedirs(os.path.dirname(args.log_file) or ".", exist_ok=True)

    print(f"[monitor] start t={_now_utc()} command={' '.join(args.command)}")
    print(f"[monitor] log-file {args.log_file}")

    child_env = dict(os.environ)
    child_env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        args.command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=child_env,
    )

    assert proc.stdout is not None
    last_line = ""
    last_line_at = time.monotonic()
    next_heartbeat = last_line_at + max(1, args.poll_sec)
    poll_interval = min(max(1, args.poll_sec), 2)

    with open(args.log_file, "a", encoding="utf-8") as log_fp:
        while True:
            now_ts = time.monotonic()
            ready, _, _ = select.select([proc.stdout], [], [], poll_interval)
            if ready:
                line = proc.stdout.readline()
                if line:
                    stripped = line.rstrip("\n")
                    print(stripped)
                    log_fp.write(line)
                    log_fp.flush()
                    last_line = stripped
                    last_line_at = now_ts
                elif proc.poll() is not None:
                    break
            elif proc.poll() is not None:
                break

            if now_ts >= next_heartbeat:
                idle_sec = int(max(0, now_ts - last_line_at))
                print(
                    f"[monitor] heartbeat t={_now_utc()} idle_sec={idle_sec} "
                    f"running={'yes' if proc.poll() is None else 'no'}"
                )
                if idle_sec >= args.stall_warn_sec:
                    print(
                        f"[monitor] stall-warning no-new-log-for={idle_sec}s "
                        f"last_line={last_line}"
                    )
                next_heartbeat = now_ts + max(1, args.poll_sec)

    rc = proc.wait()
    if rc == 0:
        print(f"[monitor] success t={_now_utc()}")
        return 0

    print(f"[monitor] failed exit_code={rc} t={_now_utc()} last_line={last_line}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
