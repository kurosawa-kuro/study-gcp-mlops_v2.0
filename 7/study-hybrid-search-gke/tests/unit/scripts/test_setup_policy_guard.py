from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_setup_scripts_use_canonical_and_ci_import_paths() -> None:
    deploy_all = _read("scripts/setup/deploy_all.py")
    destroy_all = _read("scripts/setup/destroy_all.py")

    assert "from scripts.ci.sync_dataform import main as sync_dataform_main" in deploy_all
    assert "from scripts.deploy.api_gke import main as deploy_api_main" in deploy_all
    assert "from scripts.setup.tf_bootstrap import main as tf_bootstrap_main" in deploy_all
    assert "from scripts.setup.tf_init import main as tf_init_main" in deploy_all
    assert "from scripts.setup.tf_plan import main as tf_plan_main" in deploy_all

    assert "from scripts.setup.seed_minimal_clean import main as seed_clean_main" in destroy_all


def test_setup_scripts_target_dev_terraform_environment() -> None:
    deploy_all = _read("scripts/setup/deploy_all.py")
    destroy_all = _read("scripts/setup/destroy_all.py")
    tf_init = _read("scripts/setup/tf_init.py")
    tf_plan = _read("scripts/setup/tf_plan.py")

    expected = (
        'Path(__file__).resolve().parents[2] / "infra" / "terraform" / "environments" / "dev"'
    )
    assert expected in deploy_all
    assert expected in destroy_all
    assert expected in tf_init
    assert expected in tf_plan


def test_api_deploy_targets_gke_rollout_path() -> None:
    api_gke = _read("scripts/deploy/api_gke.py")

    assert "kubectl" in api_gke
    assert "rollout status" in api_gke
    assert "deployment/search-api" in api_gke or 'DEPLOYMENT = "search-api"' in api_gke
    assert "gcloud run deploy" not in api_gke


def test_makefile_has_canonical_ops_targets() -> None:
    makefile = _read("Makefile")

    assert "deploy-all-direct:" in makefile
    assert "ops-search-components:" in makefile
    assert "ops-accuracy-report:" in makefile
    assert "local-accuracy-report:" in makefile
    assert "python -m scripts.ops.search_components" in makefile
    assert "python -m scripts.ops.accuracy_report" in makefile


def test_seed_and_feature_group_contract_pin_feature_timestamp() -> None:
    seed_minimal = _read("scripts/setup/seed_minimal.py")
    data_tf = _read("infra/terraform/modules/data/main.tf")
    vertex_tf = _read("infra/terraform/modules/vertex/main.tf")

    assert "feature_timestamp" in data_tf
    assert "Feature-time column required by Vertex AI Feature Group BigQuery source" in data_tf
    assert "CURRENT_TIMESTAMP()" in seed_minimal
    assert "feature_timestamp, property_id" in seed_minimal
    assert 'entity_id_columns = ["property_id"]' in vertex_tf
