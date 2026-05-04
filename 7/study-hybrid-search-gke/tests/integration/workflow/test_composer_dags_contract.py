"""Phase 7 workflow contract — Composer DAG file structural validity.

Pin DAG file syntax / dag_id == filename / 5-field cron / >=30min stagger /
KFP 2.16 module-level import 回避 / referenced scripts existence /
`pipeline/dags/` layers 隔離。
"""

from __future__ import annotations

import ast
import re
from itertools import pairwise

from tests.integration.workflow.conftest import (
    DAG_FILES,
    DAGS_DIR,
    REPO_ROOT,
)
from tests.integration.workflow.conftest import (
    read_repo_file as _read,
)


def test_dag_files_have_valid_python_syntax() -> None:
    """3 DAG file が Python として AST parse 可能 (Composer scheduler が DAG bag
    込み読みするとき構文エラーで全 DAG が止まる事故を防ぐ)。"""
    for dag_file in DAG_FILES:
        text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
        try:
            ast.parse(text, filename=str(DAGS_DIR / dag_file))
        except SyntaxError as exc:
            raise AssertionError(f"{dag_file} has invalid Python syntax: {exc}") from exc


def test_dag_files_pin_canonical_schedule_and_dag_id() -> None:
    """3 本 DAG の dag_id (filename と一致) + schedule + catchup=False 契約。"""
    expected_schedule = {
        "daily_feature_refresh": "0 16 * * *",
        "retrain_orchestration": "0 19 * * *",
        "monitoring_validation": "30 19 * * *",
    }
    for dag_file in DAG_FILES:
        text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
        dag_id = dag_file.removesuffix(".py")
        assert f'dag_id="{dag_id}"' in text
        assert f'schedule="{expected_schedule[dag_id]}"' in text
        assert "catchup=False" in text


def test_dag_schedules_are_valid_5_field_cron() -> None:
    """全 DAG の schedule cron が 5-field 形式 + 各 field の文字種が妥当。"""
    cron_pattern = re.compile(r'schedule="([^"]+)"')
    for dag_file in DAG_FILES:
        text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
        match = cron_pattern.search(text)
        assert match is not None
        cron = match.group(1)
        fields = cron.split()
        assert len(fields) == 5, f"{dag_file}: schedule must be 5-field cron"
        valid_field = re.compile(r"^[\d*,/\-]+$")
        for i, field in enumerate(fields):
            assert valid_field.match(field), (
                f"{dag_file}: schedule field {i} ({field!r}) has invalid characters"
            )


def test_dag_schedules_avoid_simultaneous_run() -> None:
    """3 DAG schedule が同時刻に走らず、>=30 min stagger している契約。"""
    schedules: dict[str, tuple[int, int]] = {}
    cron_pattern = re.compile(r'schedule="([^"]+)"')
    for dag_file in DAG_FILES:
        text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
        match = cron_pattern.search(text)
        assert match is not None
        cron = match.group(1)
        minute, hour, *_ = cron.split()
        schedules[dag_file.removesuffix(".py")] = (int(hour), int(minute))

    assert schedules["daily_feature_refresh"] < schedules["retrain_orchestration"]
    assert schedules["retrain_orchestration"] < schedules["monitoring_validation"]

    sorted_times = sorted(schedules.values())
    for prev, curr in pairwise(sorted_times):
        prev_minutes = prev[0] * 60 + prev[1]
        curr_minutes = curr[0] * 60 + curr[1]
        assert curr_minutes - prev_minutes >= 30


def test_dag_files_avoid_kfp_2_16_module_level_compile_import() -> None:
    """KFP 2.16 互換 issue 回避契約: DAG file が `from pipeline.workflow.compile import`
    を持たない (module-level decorator 互換 issue で TypeError)。"""
    for dag_file in DAG_FILES:
        text = (DAGS_DIR / dag_file).read_text(encoding="utf-8")
        assert "from pipeline.workflow.compile" not in text


def test_retrain_dag_is_canonical_retrain_trigger() -> None:
    """`retrain_orchestration` DAG が本線 retrain schedule を担う唯一の経路。"""
    text = (DAGS_DIR / "retrain_orchestration.py").read_text(encoding="utf-8")
    assert 'module="scripts.ops.submit_train_pipeline"' in text
    runner_text = (REPO_ROOT / "scripts/ops/submit_train_pipeline.py").read_text(encoding="utf-8")
    assert "--target" in runner_text and "train" in runner_text and "--submit" in runner_text
    for required_task in (
        "check_retrain",
        "submit_train_pipeline",
        "wait_train_succeeded",
        "promote_reranker",
    ):
        assert f'task_id="{required_task}"' in text


def test_dag_files_call_only_existing_scripts() -> None:
    """DAG が呼ぶ `python -m scripts.* / pipeline.*` の全 module が実ファイルに解決。"""
    expected_modules = {
        "scripts.infra.feature_view_sync": "scripts/infra/feature_view_sync.py",
        "scripts.setup.backfill_vector_search_index": "scripts/setup/backfill_vector_search_index.py",
        "scripts.ops.check_retrain": "scripts/ops/check_retrain.py",
        "scripts.ops.vertex.pipeline_wait": "scripts/ops/vertex/pipeline_wait.py",
        "scripts.ops.promote": "scripts/ops/promote.py",
        "scripts.ops.slo_status": "scripts/ops/slo_status.py",
        "scripts.ops.submit_train_pipeline": "scripts/ops/submit_train_pipeline.py",
        "pipeline.workflow.compile": "pipeline/workflow/compile.py",
    }
    all_dag_text = "\n".join(
        (DAGS_DIR / dag_file).read_text(encoding="utf-8") for dag_file in DAG_FILES
    )
    for module_name, file_rel in expected_modules.items():
        if module_name in all_dag_text:
            assert (REPO_ROOT / file_rel).is_file(), (
                f"DAG references python -m {module_name} but {file_rel} is missing"
            )


def test_layers_rules_isolate_pipeline_dags_from_app_imports() -> None:
    """`pipeline/dags/` は `app.*` import 禁止 (Composer worker reparse 軽量化)。"""
    from scripts.ci import layers

    assert "pipeline/dags/" in layers.DIRECTORY_RULES
    bans = layers.DIRECTORY_RULES["pipeline/dags/"]
    assert "app" in bans, "pipeline/dags/ must ban `app` import"

    # avoid unused-import lint
    _ = _read
