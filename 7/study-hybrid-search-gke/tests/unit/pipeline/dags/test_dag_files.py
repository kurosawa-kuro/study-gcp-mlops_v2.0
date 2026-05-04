"""Phase 7 W2-4 Stage 2: pipeline/dags/*.py の AST + 構造 sanity check.

Composer (Airflow Gen 3) は Composer worker 上で実行されるため、ローカル CI で
は **`apache-airflow` を依存に入れず**、AST + 文字列 / 正規表現でファイルの
構造的妥当性だけを pin する。

検証内容:
- `ast.parse` が通る (= 構文 OK)
- 各 DAG file が `dag_id="<filename stem>"` を文字列リテラルで持つ
- 各 DAG file に `schedule=` リテラルが存在
- 各 DAG file に `catchup=False` が存在 (PDCA で再 deploy しても backfill しない契約)
- 各 DAG file が `BashOperator` を使っていない (V5 fix 2026-05-03、§4.1):
  Composer worker に uv / repo source が無く `BashOperator: uv run python -m`
  は task SUCCEEDED 未達 (canonical 違反)。代わりに `KubernetesPodOperator`
  (composer-runner image 経由) を使う。
- `retrain_orchestration` の `submit_train_pipeline` が **compile を Pod 内で実行**
  し module-level import しない契約 (KFP 2.16 互換 issue 回避)。実行本体は
  `scripts.ops.submit_train_pipeline` が ``pipeline.workflow.compile`` を呼ぶ (V5-8:
  argv の shell 変数リテラル排除)
- `monitoring_validation` の SQL path 文字列が `infra/sql/monitoring/*.sql` の
  実ファイルを指す

apache-airflow を入れない理由は `pipeline/dags/_common.py` の docstring 参照。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
DAGS_DIR = REPO_ROOT / "pipeline" / "dags"

DAG_FILES = ("daily_feature_refresh.py", "retrain_orchestration.py", "monitoring_validation.py")


@pytest.mark.parametrize("dag_file", DAG_FILES)
def test_dag_file_is_syntactically_valid(dag_file: str) -> None:
    text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
    ast.parse(text)


@pytest.mark.parametrize("dag_file", DAG_FILES)
def test_dag_id_matches_filename_stem(dag_file: str) -> None:
    expected_dag_id = dag_file.removesuffix(".py")
    text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
    assert f'dag_id="{expected_dag_id}"' in text, (
        f"{dag_file}: expected dag_id literal '{expected_dag_id}' not found "
        "(file stem and dag_id must match)"
    )


@pytest.mark.parametrize("dag_file", DAG_FILES)
def test_dag_has_schedule_and_catchup_false(dag_file: str) -> None:
    text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
    schedule_match = re.search(r'schedule="([^"]+)"', text)
    assert schedule_match is not None, f"{dag_file}: schedule= literal not found"
    assert "catchup=False" in text, (
        f"{dag_file}: catchup=False not set — re-deploy で backfill が走る危険"
    )


@pytest.mark.parametrize("dag_file", DAG_FILES)
def test_dag_does_not_use_bash_operator(dag_file: str) -> None:
    """V5 fix (2026-05-03、§4.1): BashOperator + uv run は禁止。

    Composer worker に uv / repo source が無いため `BashOperator(bash_command="uv
    run python -m ...")` は確実に task SUCCEEDED せず canonical (本線 retrain =
    Composer DAG) を裏切る。代わりに `KubernetesPodOperator` (composer-runner
    image) または provider 提供 Operator (DataformCreateWorkflowInvocationOperator
    / BigQueryInsertJobOperator 等) を使う契約。
    """
    text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
    assert "from airflow.operators.bash import BashOperator" not in text, (
        f"{dag_file}: BashOperator は禁止 (V5 fix §4.1、Composer worker 非互換)"
    )
    assert "BashOperator(" not in text, (
        f"{dag_file}: BashOperator() インスタンス化は禁止 (V5 fix §4.1)"
    )
    assert "uv run python" not in text, (
        f"{dag_file}: 'uv run python' は禁止 (Composer worker に uv 不在)"
    )


def test_retrain_orchestration_invokes_compile_via_pod_runner_not_import() -> None:
    """KFP 2.16 互換 issue 回避: scheduler が DAG parse 時に `pipeline.workflow.compile`
    を import しない契約。Pod 内では `scripts.ops.submit_train_pipeline` が
    `pipeline.workflow.compile` を呼ぶ (V5-8: ``$(GCP_PROJECT)`` argv リテラル排除)。
    """
    text = (DAGS_DIR / "retrain_orchestration.py").read_text(encoding="utf-8")
    assert 'module="scripts.ops.submit_train_pipeline"' in text, (
        "retrain_orchestration::submit_train_pipeline must use "
        'python_pod(module="scripts.ops.submit_train_pipeline", ...) (V5-8)'
    )
    assert "from pipeline.workflow.compile" not in text, (
        "retrain_orchestration must NOT import pipeline.workflow.compile directly "
        "(KFP 2.16 互換 issue で module load 段で TypeError)"
    )
    runner = REPO_ROOT / "scripts/ops/submit_train_pipeline.py"
    runner_text = runner.read_text(encoding="utf-8")
    assert "--target" in runner_text and "--submit" in runner_text, (
        "submit_train_pipeline runner must forward compile argv (V5-8)"
    )


@pytest.mark.parametrize("dag_file", DAG_FILES)
def test_dag_uses_pod_or_provider_operator(dag_file: str) -> None:
    """V5 fix: 各 DAG は KubernetesPodOperator (= python_pod helper 経由)
    または Airflow provider 提供 Operator (DataformCreateWorkflowInvocationOperator
    / BigQueryInsertJobOperator 等) のみで task を構成する契約。"""
    text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
    uses_python_pod = "python_pod(" in text
    uses_provider_op = (
        "DataformCreateWorkflowInvocationOperator" in text
        or "BigQueryInsertJobOperator" in text
        or "ShortCircuitOperator" in text  # gate のみは python callable 可
    )
    assert uses_python_pod or uses_provider_op, (
        f"{dag_file}: KubernetesPodOperator (python_pod) or Airflow provider "
        "Operator のいずれかを使うこと (BashOperator は §4.1 で禁止)"
    )


def test_monitoring_validation_sql_paths_resolve_to_real_files() -> None:
    """`monitoring_validation.py` が参照する SQL path が実ファイルに解決すること。"""
    monitoring_dir = REPO_ROOT / "infra" / "sql" / "monitoring"
    assert (monitoring_dir / "validate_feature_skew.sql").is_file(), (
        "validate_feature_skew.sql is missing — DAG monitoring_validation depends on it"
    )
    assert (monitoring_dir / "validate_model_output_drift.sql").is_file(), (
        "validate_model_output_drift.sql is missing — DAG monitoring_validation depends on it"
    )

    text = (DAGS_DIR / "monitoring_validation.py").read_text(encoding="utf-8")
    assert "validate_feature_skew.sql" in text
    assert "validate_model_output_drift.sql" in text


def test_all_dag_files_present() -> None:
    """`pipeline/dags/` 配下に必須 4 ファイル + __init__.py + _pod.py が揃っている。"""
    expected = {"__init__.py", "_common.py", "_pod.py", *DAG_FILES}
    actual = {p.name for p in DAGS_DIR.glob("*.py")}
    missing = expected - actual
    assert not missing, f"missing DAG files: {sorted(missing)}"
