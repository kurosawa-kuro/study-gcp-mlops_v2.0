"""Phase 7 canonical orchestration DAG #1: daily_feature_refresh.

責務: 日次で feature 系のデータを refresh:
1. Dataform workflow 実行 (`feature_mart.property_features_daily` など再計算)
2. Vertex AI Feature View sync (Feature Online Store 更新)
3. (opt-in) Vertex Vector Search incremental backfill

schedule: `0 16 * * *` UTC = 01:00 JST。`retrain_orchestration` (04:00 JST)
の 3 時間前に feature を refresh しておくため、本 DAG が先行する。

**V5 fix (2026-05-03)**: 旧版は BashOperator + subprocess で `python -m ...` を
Composer worker 上で実行しようとしていたが、Composer worker に必要 venv が無く
task SUCCEEDED 未達 (canonical 違反)。新版は `KubernetesPodOperator` +
`composer-runner` image で実行 (= V5 = §4.1)。Dataform は Composer Gen 3 組み
込みの `DataformCreateWorkflowInvocationOperator` を使う (= gcloud CLI 不要、
retry / state 管理が provider 側で処理される)。
"""

from __future__ import annotations

import os

from airflow import DAG
from airflow.operators.python import ShortCircuitOperator
from airflow.providers.google.cloud.operators.dataform import (
    DataformCreateCompilationResultOperator,
    DataformCreateWorkflowInvocationOperator,
)

from pipeline.dags._common import DEFAULT_DAG_ARGS, env, fixed_start_date
from pipeline.dags._pod import python_pod


def _gate_daily_vvs_refresh() -> bool:
    """`ENABLE_DAILY_VVS_REFRESH=true` のときだけ後段を走らせる short-circuit。"""
    return env("ENABLE_DAILY_VVS_REFRESH", "false").lower() == "true"


# Dataform repository は terraform で `hybrid-search-cloud` を作成済 (data module)。
# main branch の workspace を compile + invoke する。
DATAFORM_REPO = env("DATAFORM_REPO_ID", "hybrid-search-cloud")
DATAFORM_REGION = env("REGION", "asia-northeast1")
# Composer Gen 3 が GCP_PROJECT を auto-set。
PROJECT_ID = os.environ.get("GCP_PROJECT") or os.environ.get("PROJECT_ID") or ""


with DAG(
    dag_id="daily_feature_refresh",
    description="Phase 7 canonical: Dataform run + Feature View sync + (opt) VVS incremental backfill",
    default_args=DEFAULT_DAG_ARGS,
    schedule="0 16 * * *",
    start_date=fixed_start_date(),
    catchup=False,
    tags=["phase7", "canonical", "feature"],
) as dag:
    # Dataform compile + invocation (= `gcloud dataform repositories
    # workflow-invocations create` に相当、provider が REST API を叩く)。
    dataform_compile = DataformCreateCompilationResultOperator(
        task_id="dataform_compile",
        project_id=PROJECT_ID,
        region=DATAFORM_REGION,
        repository_id=DATAFORM_REPO,
        compilation_result={
            "git_commitish": "main",
        },
    )

    dataform_run = DataformCreateWorkflowInvocationOperator(
        task_id="dataform_run",
        project_id=PROJECT_ID,
        region=DATAFORM_REGION,
        repository_id=DATAFORM_REPO,
        workflow_invocation={
            "compilation_result": ("{{ task_instance.xcom_pull('dataform_compile')['name'] }}"),
        },
    )

    trigger_fv_sync = python_pod(
        task_id="trigger_fv_sync",
        module="scripts.infra.feature_view_sync",
    )

    gate_vvs_refresh = ShortCircuitOperator(
        task_id="gate_vvs_refresh",
        python_callable=_gate_daily_vvs_refresh,
    )

    backfill_vvs_incremental = python_pod(
        task_id="backfill_vvs_incremental",
        module="scripts.setup.backfill_vector_search_index",
        extra_args=["--apply"],
    )

    (
        dataform_compile
        >> dataform_run
        >> trigger_fv_sync
        >> gate_vvs_refresh
        >> backfill_vvs_incremental
    )
