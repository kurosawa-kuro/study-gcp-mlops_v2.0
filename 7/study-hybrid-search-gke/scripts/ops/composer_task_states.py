"""Parse `gcloud composer environments run ... tasks states-for-dag-run` output.

`gcloud composer environments run` prints log lines and banners *before* the
JSON array — including ``Executing the command: [ airflow ... ]`` (a non-JSON
bracket group). Piping stdout to ``json.load`` then fails with JSONDecodeError.
This module takes the **task payload** starting at ``[{`` (array of objects) and
decodes it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence

from scripts._common import env, fail


def _balanced_array_from(text: str, start: int) -> str:
    """Return balanced `[` … `]` substring starting at ``start`` (string-aware)."""
    depth = 0
    in_str = False
    esc = False
    str_quote: str | None = None
    for j in range(start, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == str_quote:
                in_str = False
                str_quote = None
            continue
        if c in ("'", '"'):
            in_str = True
            str_quote = c
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    raise ValueError("unclosed JSON array in gcloud output")


def extract_json_array(text: str) -> str:
    """Return the JSON array from gcloud output.

    Skips the banner ``Executing the command: [ airflow ... ]`` (first ``[`` is
    not task JSON). Real payloads start with ``[{`` (array of objects).
    """
    i = text.find("[{")
    if i >= 0:
        return _balanced_array_from(text, i)
    # Empty array or whitespace-only
    m = re.search(r"\[\s*\]", text)
    if m:
        return m.group(0)
    i = text.find("[")
    if i < 0:
        raise ValueError("no JSON array in gcloud output (empty or wrong command)")
    return _balanced_array_from(text, i)


def _gcloud_composer(
    subcommand_after_run: Sequence[str],
    *,
    project_id: str,
    region: str,
    composer_env: str,
) -> str:
    cmd: list[str] = [
        "gcloud",
        "composer",
        "environments",
        "run",
        composer_env,
        f"--project={project_id}",
        f"--location={region}",
        *subcommand_after_run,
    ]
    # Composer API + remote Airflow can exceed 1-2 min; fail fast with a clear error.
    proc = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=300)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 and "[" not in out:
        raise RuntimeError(f"gcloud failed rc={proc.returncode}: {out[-2000:]}")
    return out


def _latest_run_id_from_list_runs(text: str) -> str | None:
    """Best-effort parse of `airflow dags list-runs` table text (newest row first)."""
    for line in text.splitlines():
        # Column widths truncate dag_id; match run_id cells anywhere on the line.
        m = re.search(r"\b(manual__[^\s|]+|scheduled__[^\s|]+)", line)
        if m:
            return m.group(1).strip()
    return None


def fetch_task_states_json(
    *,
    dag_id: str,
    run_id: str,
    project_id: str,
    region: str,
    composer_env: str,
) -> list[dict[str, object]]:
    out = _gcloud_composer(
        [
            "tasks",
            "states-for-dag-run",
            "--",
            "-o",
            "json",
            dag_id,
            run_id,
        ],
        project_id=project_id,
        region=region,
        composer_env=composer_env,
    )
    raw = extract_json_array(out)
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("expected JSON array from states-for-dag-run")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dag-id", default="retrain_orchestration")
    parser.add_argument(
        "--run-id", default="", help="DAG run id (manual__...). Omit with --latest."
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Resolve run_id from `dags list-runs` (first row for dag-id).",
    )
    args = parser.parse_args()

    project_id = env("PROJECT_ID", "mlops-dev-a")
    region = env("REGION", "asia-northeast1")
    composer_env = env("COMPOSER_ENV", "hybrid-search-orchestrator")

    run_id = (args.run_id or "").strip()
    if args.latest or not run_id:
        table = _gcloud_composer(
            ["dags", "list-runs", "--", "--dag-id", args.dag_id],
            project_id=project_id,
            region=region,
            composer_env=composer_env,
        )
        rid = _latest_run_id_from_list_runs(table)
        if not rid:
            return fail("could not parse run_id from list-runs; pass --run-id explicitly")
        run_id = rid
        print(f"[info] using run_id={run_id}", file=sys.stderr)

    try:
        rows = fetch_task_states_json(
            dag_id=args.dag_id,
            run_id=run_id,
            project_id=project_id,
            region=region,
            composer_env=composer_env,
        )
    except (json.JSONDecodeError, ValueError, RuntimeError) as exc:
        return fail(f"{exc}")

    for row in sorted(rows, key=lambda r: str(r.get("task_id", ""))):
        tid = row.get("task_id", "")
        st = row.get("state")
        print(f"{tid}\t{st}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
