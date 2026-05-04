"""Phase 7 workflow contract — Cloud Composer Terraform module + IAM SA + Make targets.

Pin the Composer module skeleton, IAM `sa-composer` SA + roles, dev environment
wiring (variables / outputs / depends_on), Make target inventory, deploy_all
step integration, env-variable propagation, image_version validity, workloads
config, cost guards, and Stage 3 default flips.

DAG file の構造 contract は `test_composer_dags_contract.py` を参照。
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

from scripts.deploy import composer_deploy_dags
from scripts.setup import deploy_all
from tests.integration.workflow.conftest import COMPOSER_MODULE_DIR
from tests.integration.workflow.conftest import read_repo_file as _read


def test_composer_module_exists_with_required_files() -> None:
    """Phase 7 W2-4 Stage 1: `infra/terraform/modules/composer/` 必須 4 ファイル。"""
    assert COMPOSER_MODULE_DIR.is_dir(), "infra/terraform/modules/composer/ is missing"
    for required in ("main.tf", "variables.tf", "outputs.tf", "versions.tf"):
        assert (COMPOSER_MODULE_DIR / required).is_file(), f"composer module missing {required}"


def test_composer_module_uses_gen3_image_with_enable_flag_gate() -> None:
    """Composer 環境は Gen 3 image + `enable_composer` flag で count gate。"""
    main_tf = _read("infra/terraform/modules/composer/main.tf")
    assert 'image_version = "composer-3-airflow-' in main_tf
    assert "count    = var.enable_composer ? 1 : 0" in main_tf, (
        "composer environment must be count-gated by var.enable_composer"
    )
    for required_env in (
        "REGION",
        "VERTEX_LOCATION",
        "PIPELINE_ROOT_BUCKET",
        "VERTEX_VECTOR_SEARCH_INDEX_RESOURCE_NAME",
        "VERTEX_FEATURE_ONLINE_STORE_ID",
        "VERTEX_FEATURE_VIEW_ID",
    ):
        assert required_env in main_tf


def test_composer_env_variables_avoid_reserved_names() -> None:
    """**Composer 予約変数禁止 契約** (2026-05-03 追加): `env_variables` に
    Composer Gen 3 の予約 environment variable を含めると HTTP 400
    `Environment variables [X] may not be overridden` で create が拒否される。

    過去事故: `PROJECT_ID = var.project_id` を入れた状態で deploy-all 実行
    → step 6 stage1 apply の Composer 作成で 400 → step 6 完走に 30 min ロス
    + state 半分作成の片付けコスト。Composer 自動設定の `GCP_PROJECT` を DAG
    側で参照する設計 (`pipeline/dags/_common.py::project_id`)。
    """
    main_tf = _read("infra/terraform/modules/composer/main.tf")
    common_py = _read("pipeline/dags/_common.py")

    reserved = (
        "PROJECT_ID",
        "GCP_PROJECT",
        "AIRFLOW_HOME",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
        "PATH",
        "DAGS_FOLDER",
        "GCS_BUCKET",
    )
    env_block_match = re.search(r"env_variables\s*=\s*\{[^}]*\}", main_tf, flags=re.DOTALL)
    assert env_block_match is not None, "composer main.tf must declare an env_variables block"
    env_block = env_block_match.group(0)
    for reserved_name in reserved:
        key_pattern = re.compile(rf"^\s*{re.escape(reserved_name)}\s*=", flags=re.MULTILINE)
        assert key_pattern.search(env_block) is None, (
            f"composer env_variables must NOT include reserved name {reserved_name!r} "
            "(Composer Gen 3 returns HTTP 400 'may not be overridden')"
        )
    assert 'env("GCP_PROJECT")' in common_py, (
        "DAG helper must read project ID via auto-set GCP_PROJECT, not user-set PROJECT_ID"
    )


def test_composer_image_version_is_known_supported_form() -> None:
    """Composer image_version の文字列形式が正しいこと (Gen 3、`composer-3-airflow-X.Y.Z[-build.N]`)。"""
    composer_main = _read("infra/terraform/modules/composer/main.tf")
    match = re.search(r'image_version\s*=\s*"([^"]+)"', composer_main)
    assert match is not None
    image_version = match.group(1)
    assert image_version.startswith("composer-3-")
    assert "-airflow-" in image_version


def test_composer_environment_uses_correct_region_var() -> None:
    """`region` は `var.region` を使う (`var.vertex_location` と取り違えで egress 課金)。"""
    composer_main = _read("infra/terraform/modules/composer/main.tf")
    assert (
        "region   = var.region" in composer_main
        or "region  = var.region" in composer_main
        or "region = var.region" in composer_main
    )


def test_composer_environment_has_proper_create_destroy_timeouts() -> None:
    """Composer 環境作成 15-25 min かかるため、provider default 30m では足りない場合がある。"""
    composer_main = _read("infra/terraform/modules/composer/main.tf")
    assert 'create = "60m"' in composer_main
    assert 'delete = "30m"' in composer_main


def test_composer_workloads_have_max_count_to_bound_cost() -> None:
    """Composer worker `max_count` 指定で autoscaling 上限を pin (コスト爆発防止)。"""
    composer_main = _read("infra/terraform/modules/composer/main.tf")
    worker_match = re.search(
        r"worker\s*\{[^}]*max_count\s*=\s*(\d+)",
        composer_main,
        flags=re.DOTALL,
    )
    assert worker_match is not None
    max_count = int(worker_match.group(1))
    assert 1 <= max_count <= 5, (
        f"Composer worker.max_count={max_count} is outside sane range for dev (1-5)"
    )


def test_composer_module_workloads_config_has_scheduler_web_worker() -> None:
    composer_main = _read("infra/terraform/modules/composer/main.tf")
    for required in ("scheduler {", "web_server {", "worker {"):
        assert required in composer_main


def test_composer_module_outputs_dag_bucket_and_airflow_uri() -> None:
    outputs_tf = _read("infra/terraform/modules/composer/outputs.tf")
    for required_output in (
        'output "dag_bucket"',
        'output "airflow_uri"',
        'output "environment_name"',
    ):
        assert required_output in outputs_tf


def test_composer_module_wired_into_dev_environment_with_correct_depends_on() -> None:
    """`module "composer"` が iam / data / vector_search / vertex に depends_on 接続。"""
    main_tf = _read("infra/terraform/environments/dev/main.tf")
    assert 'module "composer" {' in main_tf
    assert 'source = "../../modules/composer"' in main_tf
    composer_block_match = re.search(r'module "composer" \{(.+?)\n\}\n', main_tf, flags=re.DOTALL)
    assert composer_block_match is not None
    block = composer_block_match.group(1)
    for required_dep in ("module.iam", "module.data", "module.vector_search", "module.vertex"):
        assert required_dep in block


def test_composer_module_passes_required_terraform_inputs() -> None:
    """`module "composer"` が必須 input 全てを渡している。"""
    main_tf = _read("infra/terraform/environments/dev/main.tf")
    composer_block_match = re.search(r'module "composer" \{(.+?)\n\}\n', main_tf, flags=re.DOTALL)
    assert composer_block_match is not None
    block = composer_block_match.group(1)
    required_inputs = (
        "enable_composer",
        "project_id",
        "region",
        "vertex_location",
        "environment_name",
        "composer_service_account_email",
        "pipeline_root_bucket_name",
        "vector_search_index_resource_name",
        "feature_online_store_id",
        "feature_view_id",
    )
    for required in required_inputs:
        assert required in block, f"module composer missing required input: {required}"


def test_dev_environment_has_composer_variables_and_outputs() -> None:
    variables_tf = _read("infra/terraform/environments/dev/variables.tf")
    outputs_tf = _read("infra/terraform/environments/dev/outputs.tf")

    for required_var in (
        'variable "enable_composer"',
        'variable "composer_environment_name"',
        'variable "pipeline_template_gcs_path"',
    ):
        assert required_var in variables_tf

    for required_output in (
        'output "composer_dag_bucket"',
        'output "composer_airflow_uri"',
        'output "composer_environment_name"',
    ):
        assert required_output in outputs_tf


def test_enable_composer_default_is_flipped_to_true() -> None:
    """Stage 3 で `enable_composer` default を true に flip 済 (canonical 運用契約)。"""
    variables_tf = _read("infra/terraform/environments/dev/variables.tf")
    enable_block_match = re.search(
        r'variable "enable_composer" \{(.+?)\n\}', variables_tf, flags=re.DOTALL
    )
    assert enable_block_match is not None
    block = enable_block_match.group(1)
    assert "default     = true" in block or "default = true" in block


def test_iam_module_provisions_sa_composer_with_required_roles() -> None:
    iam_main = _read("infra/terraform/modules/iam/main.tf")
    iam_outputs = _read("infra/terraform/modules/iam/outputs.tf")

    assert 'resource "google_service_account" "composer" {' in iam_main
    assert 'account_id   = "sa-composer"' in iam_main

    for required_role in (
        '"roles/composer.worker"',
        '"roles/aiplatform.user"',
        '"roles/bigquery.jobUser"',
        '"roles/bigquery.dataViewer"',
        '"roles/run.invoker"',
    ):
        assert required_role in iam_main

    assert "google_project_iam_member" in iam_main and '"roles/composer.admin"' in iam_main, (
        "github_deployer must have roles/composer.admin to provision Composer env"
    )

    assert "composer          = google_service_account.composer" in iam_outputs


def test_composer_sa_used_in_workload_identity_binding_chain() -> None:
    """`sa-composer` が Composer module + IAM module + outputs map の 3 箇所で
    lockstep に登録されていること。"""
    iam_main = _read("infra/terraform/modules/iam/main.tf")
    iam_outputs = _read("infra/terraform/modules/iam/outputs.tf")
    dev_main = _read("infra/terraform/environments/dev/main.tf")

    assert 'resource "google_service_account" "composer"' in iam_main
    assert 'account_id   = "sa-composer"' in iam_main
    assert "composer          = google_service_account.composer" in iam_outputs
    assert "module.iam.service_accounts.composer.email" in dev_main


def test_composer_sa_email_consumed_by_module() -> None:
    main_tf = _read("infra/terraform/environments/dev/main.tf")
    assert "module.iam.service_accounts.composer.email" in main_tf


def test_tf_apply_stage1_targets_includes_module_composer() -> None:
    """`module.composer` は `TF_APPLY_STAGE1_TARGETS` に含まれること。"""
    from scripts.infra.terraform_stage_apply import TF_APPLY_STAGE1_TARGETS

    assert "module.composer" in TF_APPLY_STAGE1_TARGETS


def test_composer_deploy_dags_step_inserted_between_overlay_and_deploy_api() -> None:
    """deploy_all の `composer-deploy-dags` step は overlay-configmap / deploy-api 間。"""
    steps = deploy_all._steps()
    names = [step.name for step in steps]

    assert "composer-deploy-dags" in names
    composer_idx = names.index("composer-deploy-dags")
    overlay_idx = names.index("overlay-configmap")
    deploy_api_idx = names.index("deploy-api")

    assert overlay_idx < composer_idx < deploy_api_idx

    composer_step = next(s for s in steps if s.name == "composer-deploy-dags")
    assert composer_step.run is deploy_all._run_composer_deploy_dags


def test_deploy_all_step_runner_imports_composer_deploy_dags() -> None:
    deploy_all_py = _read("scripts/setup/deploy_all.py")
    assert (
        "from scripts.deploy.composer_deploy_dags import main as composer_deploy_dags_main"
        in deploy_all_py
    )
    assert "def _run_composer_deploy_dags() -> int:" in deploy_all_py
    assert "return composer_deploy_dags_main()" in deploy_all_py


def test_composer_deploy_dags_early_returns_when_disabled(monkeypatch) -> None:
    """`enable_composer=false` → terraform output `composer_dag_bucket` 空 →
    rc=0 で skip (Stage 1/Stage 2 互換契約)。"""
    import json as _json
    import subprocess

    def _fake_run(cmd, capture=False, check=False):
        proc = subprocess.CompletedProcess(cmd, returncode=0, stdout=_json.dumps({}))
        return proc

    monkeypatch.setattr(composer_deploy_dags, "run", _fake_run)
    assert composer_deploy_dags.main() == 0


def test_composer_deploy_dags_uses_gsutil_m_for_parallel_upload() -> None:
    deploy_script = _read("scripts/deploy/composer_deploy_dags.py")
    assert '"-m"' in deploy_script and '"cp"' in deploy_script


def test_composer_dag_bucket_terraform_output_consumed_by_deploy_script() -> None:
    """`composer_dag_bucket` output 名が deploy script と outputs.tf で同一。"""
    deploy_script = _read("scripts/deploy/composer_deploy_dags.py")
    outputs_tf = _read("infra/terraform/environments/dev/outputs.tf")
    composer_outputs_tf = _read("infra/terraform/modules/composer/outputs.tf")

    assert '_terraform_output("composer_dag_bucket")' in deploy_script
    assert 'output "composer_dag_bucket" {' in outputs_tf
    assert 'output "dag_bucket" {' in composer_outputs_tf
    assert "module.composer.dag_bucket" in outputs_tf


def test_makefile_exposes_composer_deploy_dags_and_smoke_targets() -> None:
    makefile = _read("Makefile")

    for required_target in (
        "composer-deploy-dags",
        "ops-composer-trigger",
        "ops-composer-list-runs",
        "ops-composer-task-states",
    ):
        assert f"{required_target}:" in makefile, f"Make target {required_target} missing"
        assert required_target in makefile.split(".PHONY")[1]

    assert "uv run python -m scripts.deploy.composer_deploy_dags" in makefile
    assert "uv run python -m scripts.ops.composer_task_states" in makefile
    assert "gcloud composer environments run" in makefile
    assert "COMPOSER_ENV  ?= " in makefile


def test_composer_runner_dockerfile_does_not_bake_setting_yaml() -> None:
    """Incident: baking env/config/setting.yaml invites wrong ops; live env is canonical."""
    dockerfile = _read("infra/run/services/composer_runner/Dockerfile")
    assert "setting.yaml" in dockerfile
    # Hard guard: no COPY of repo env/config into the image
    for line in dockerfile.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("COPY") and "env/config" in stripped:
            raise AssertionError(
                "composer-runner Dockerfile must not COPY env/config "
                f"(setting drift risk): {line!r}"
            )


def test_make_composer_env_default_matches_terraform_default() -> None:
    """`Makefile::COMPOSER_ENV` ↔ tf `composer_environment_name` mismatch なし。"""
    makefile = _read("Makefile")
    variables_tf = _read("infra/terraform/environments/dev/variables.tf")

    make_match = re.search(r"COMPOSER_ENV\s+\?=\s+(\S+)", makefile)
    assert make_match is not None
    make_default = make_match.group(1).strip()

    tf_match = re.search(
        r'variable "composer_environment_name" \{[^}]*default\s+=\s+"([^"]+)"',
        variables_tf,
        flags=re.DOTALL,
    )
    assert tf_match is not None
    tf_default = tf_match.group(1)

    assert make_default == tf_default


def test_pyproject_does_not_pull_apache_airflow_into_runtime() -> None:
    """`apache-airflow` は Composer worker で動く想定 — runtime / dev deps 不要。"""
    pyproject = _read("pyproject.toml")
    main_deps_match = re.search(
        r"^dependencies\s*=\s*\[(.*?)\]",
        pyproject,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert main_deps_match is not None
    main_deps = main_deps_match.group(1)
    assert "apache-airflow" not in main_deps, (
        "apache-airflow must NOT be in [project] dependencies (Composer worker only). "
        "Test DAG file structure via AST + string parsing instead."
    )


# Suppress unused-import warning for MagicMock — we keep it available for
# subclasses if helper tests are added.
_ = MagicMock
