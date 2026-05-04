"""Thin ``bq query`` wrapper for the BQML popularity training SQL.

Keeps the Python runner stdlib-only (per scripts/README.md). The SQL file
itself lives at ``scripts/bqml/train_popularity.sql`` so operators can
also run it by hand from the BigQuery console when debugging.
"""

from __future__ import annotations

from pathlib import Path

from scripts._common import env, fail, run

SQL_PATH = Path("scripts/bqml/train_popularity.sql")


def main() -> int:
    project_id = env("PROJECT_ID")
    if not project_id:
        return fail("PROJECT_ID not set (env/config/setting.yaml or env var)")

    if not SQL_PATH.exists():
        return fail(f"BQML SQL not found at {SQL_PATH}")
    sql = SQL_PATH.read_text(encoding="utf-8")
    proc = run(
        [
            "bq",
            f"--project_id={project_id}",
            "query",
            "--use_legacy_sql=false",
            "--nouse_cache",
            sql,
        ],
        check=False,
    )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
