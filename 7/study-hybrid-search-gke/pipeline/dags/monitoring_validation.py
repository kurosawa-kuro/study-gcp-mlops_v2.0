"""Phase 7 canonical orchestration DAG #3: monitoring_validation.

責務: 日次で feature skew / model output drift / SLO + burn-rate を確認:
1. `validate_feature_skew.sql` を BigQuery で実行 → `mlops.validation_results`
2. `validate_model_output_drift.sql` を BigQuery で実行 → `mlops.model_monitoring_alerts`
3. SLO + burn-rate alert 確認 (`scripts.ops.slo_status`)

schedule: `30 19 * * *` UTC = 04:30 JST (`retrain_orchestration` の 30 分後)。

詳細: docs/architecture/01_仕様と設計.md §3 / §3.5 (Phase 6 6B PMLE 増設)。

**V5 fix (2026-05-03)**: `check_slo_burn_rate` を BashOperator + subprocess
(Composer worker 上で `python -m` 実行を試みていた) から `KubernetesPodOperator`
(composer-runner image 経由) に置き換え。BQ 系の 2 task は元から
`BigQueryInsertJobOperator` で問題なし。

SQL ファイル参照 (2026-05-03 incident 対策): Composer 上では DAG file は
``/home/airflow/gcs/dags/monitoring_validation.py`` に置かれ、repo の
``infra/sql/`` は存在しない。本 DAG は **Composer data folder** (= GCS
``data/`` サブパス、Composer pod の ``/home/airflow/gcs/data/`` に mount)
を一次参照、ローカル repo (`scripts/deploy/composer_deploy_dags.py` から
の DAG smoke / pytest) を fallback として開く構造に分離する。
"""

from __future__ import annotations

from pathlib import Path

from airflow import DAG
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator

from pipeline.dags._common import DEFAULT_DAG_ARGS, fixed_start_date
from pipeline.dags._pod import python_pod

COMPOSER_DATA_ROOT = Path("/home/airflow/gcs/data")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_sql_path(relative: str) -> Path:
    """Resolve SQL path against Composer ``data/`` first, repo fallback second."""
    composer_path = COMPOSER_DATA_ROOT / relative
    if composer_path.exists():
        return composer_path
    return REPO_ROOT / relative


SKEW_SQL_PATH = _resolve_sql_path("infra/sql/monitoring/validate_feature_skew.sql")
DRIFT_SQL_PATH = _resolve_sql_path("infra/sql/monitoring/validate_model_output_drift.sql")


with DAG(
    dag_id="monitoring_validation",
    description="Phase 7 canonical: feature skew + model output drift + SLO burn-rate",
    default_args=DEFAULT_DAG_ARGS,
    schedule="30 19 * * *",
    start_date=fixed_start_date(),
    catchup=False,
    tags=["phase7", "canonical", "monitoring"],
) as dag:
    run_feature_skew = BigQueryInsertJobOperator(
        task_id="run_feature_skew",
        configuration={
            "query": {
                "query": SKEW_SQL_PATH.read_text(encoding="utf-8"),
                "useLegacySql": False,
            },
        },
    )

    run_model_output_drift = BigQueryInsertJobOperator(
        task_id="run_model_output_drift",
        configuration={
            "query": {
                "query": DRIFT_SQL_PATH.read_text(encoding="utf-8"),
                "useLegacySql": False,
            },
        },
    )

    check_slo_burn_rate = python_pod(
        task_id="check_slo_burn_rate",
        module="scripts.ops.slo_status",
    )

    [run_feature_skew, run_model_output_drift] >> check_slo_burn_rate
