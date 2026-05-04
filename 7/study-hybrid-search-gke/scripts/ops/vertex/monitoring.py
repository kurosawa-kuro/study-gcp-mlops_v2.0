"""Read recent drift alerts from BigQuery.

Phase 6 used Vertex Model Monitoring v2 as the primary writer into
``mlops.model_monitoring_alerts``. Phase 7 keeps the same sink table but
adds a self-managed Scheduled Query that derives drift from
``mlops.ranking_log`` because live serving moved to GKE + KServe.

This script lists the last N rows so an operator can confirm the current
drift pipeline is firing (and surfacing genuine signals, not just an empty
table).

Usage::

    LIMIT=10 make ops-vertex-monitoring

Exit codes:
    0  — query succeeded (alerts table reachable, regardless of rowcount)
    1  — config / IAM error
"""

from __future__ import annotations

import os

from scripts._common import env, fail


def main() -> int:
    project_id = env("PROJECT_ID")
    dataset = env("BQ_DATASET_MLOPS", "mlops")
    table = env("BQ_TABLE_MODEL_MONITORING_ALERTS", "model_monitoring_alerts")
    limit = int(os.environ.get("LIMIT", "10"))
    if not project_id:
        return fail("vertex-monitoring: PROJECT_ID is required")

    from google.cloud import bigquery

    fq = f"`{project_id}.{dataset}.{table}`"
    sql = f"""
        SELECT *
        FROM {fq}
        ORDER BY alert_time DESC
        LIMIT {limit}
    """
    client = bigquery.Client(project=project_id)
    try:
        rows = list(client.query(sql).result())
    except Exception as exc:
        return fail(f"vertex-monitoring: BQ query failed: {exc}")

    print(f"vertex-monitoring: {len(rows)} alert row(s) from {fq} (latest {limit})")
    if not rows:
        print(
            "  HINT: empty table is normal pre-rollout. "
            "After the Scheduled Query / any endpoint-based monitoring runs, "
            "the table fills up."
        )
        return 0

    for r in rows:
        print(f"  {dict(r)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
