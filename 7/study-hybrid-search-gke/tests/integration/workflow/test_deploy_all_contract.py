"""Phase 7 workflow contract — `make deploy-all` step sequence + ordering.

Pin the one-shot PDCA path, ConfigMap overlay → live Vertex outputs, the
`make run-all-core` validation order, and the local-boot ADC-free contract.
"""

from __future__ import annotations

import re
import subprocess
from unittest.mock import patch

from app.composition_root import ContainerBuilder
from app.services.noop_adapters import (
    NoopDataCatalogReader,
    NoopFeedbackRecorder,
    NoopRankingLogPublisher,
    NoopRetrainQueries,
)
from app.settings import ApiSettings
from scripts.deploy import configmap_overlay
from scripts.setup import deploy_all
from tests.integration.workflow.conftest import read_repo_file as _read


def test_deploy_all_step_sequence_pins_one_shot_pdca_contract() -> None:
    steps = deploy_all._steps()
    names = [step.name for step in steps]

    assert names == [
        "tf-bootstrap",
        "tf-init",
        "recover-wif",
        "sync-dataform",
        "tf-plan",
        "tf-apply",
        "seed-lgbm-model",
        "seed-test",
        "sync-meili",
        "backfill-vvs",
        "trigger-fv-sync",
        "apply-manifests",
        "overlay-configmap",
        "composer-deploy-dags",
        "deploy-api",
    ], "deploy-all drifted from the Phase 7 one-shot PDCA path"
    assert [step.number for step in steps] == list(range(1, 16))


def test_deploy_all_seed_test_runs_before_feature_view_sync() -> None:
    """**seed → FV sync 順序契約**: `seed-test` が `trigger-fv-sync` より先。
    順序逆転で FV が空のまま sync 完了 → `ops-vertex-feature-group` 404。"""
    steps = deploy_all._steps()
    names = [s.name for s in steps]
    assert names.index("seed-test") < names.index("trigger-fv-sync"), (
        "seed-test must run before trigger-fv-sync (otherwise FV syncs an empty source)"
    )
    assert names.index("seed-test") < names.index("backfill-vvs"), (
        "seed-test must run before backfill-vvs (otherwise VVS index is empty)"
    )
    assert names.index("sync-meili") < names.index("backfill-vvs")
    assert names.index("backfill-vvs") < names.index("trigger-fv-sync")
    assert names.index("trigger-fv-sync") < names.index("apply-manifests")


def test_deploy_all_overlay_configmap_runs_before_deploy_api() -> None:
    """**ConfigMap overlay → deploy-api 順序契約**: 順序逆転で新 search-api
    Pod が古い ConfigMap (placeholder URL 等) を読み `/search` が 0 件返却。"""
    steps = deploy_all._steps()
    names = [s.name for s in steps]
    assert names.index("overlay-configmap") < names.index("composer-deploy-dags")
    assert names.index("composer-deploy-dags") < names.index("deploy-api")


def test_configmap_overlay_injects_live_vertex_outputs(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setenv("REGION", "asia-northeast1")
    monkeypatch.setenv("MODELS_BUCKET", "mlops-test-models")

    captured: dict[str, str] = {}

    def _fake_generate(*, project_id: str, models_bucket: str, meili_base_url: str, **kwargs: str):
        captured["project_id"] = project_id
        captured["models_bucket"] = models_bucket
        captured["meili_base_url"] = meili_base_url
        captured.update(kwargs)
        return {"project_id": project_id}

    with (
        patch.object(
            configmap_overlay,
            "_resolve_meili_url",
            return_value="https://meili.example.run.app",
        ),
        patch.object(
            configmap_overlay,
            "_terraform_output_map",
            return_value={
                "vector_search_index_endpoint_id": "projects/x/locations/r/indexEndpoints/123",
                "vector_search_deployed_index_id": "property_embeddings_v3",
                "vertex_feature_online_store_id": "store-a",
                "vertex_feature_view_id": "view-a",
                "vertex_feature_online_store_endpoint": "store.example.com",
            },
        ),
        patch.object(configmap_overlay, "generate_configmap_data", side_effect=_fake_generate),
        patch.object(configmap_overlay, "render_configmap_yaml", return_value="apiVersion: v1\n"),
        patch.object(
            subprocess,
            "run",
            return_value=subprocess.CompletedProcess(["kubectl"], returncode=0),
        ) as run_mock,
    ):
        assert configmap_overlay.main() == 0

    assert captured == {
        "project_id": "mlops-test",
        "models_bucket": "mlops-test-models",
        "meili_base_url": "https://meili.example.run.app",
        "vertex_vector_search_index_endpoint_id": "projects/x/locations/r/indexEndpoints/123",
        "vertex_vector_search_deployed_index_id": "property_embeddings_v3",
        "vertex_feature_online_store_id": "store-a",
        "vertex_feature_view_id": "view-a",
        "vertex_feature_online_store_endpoint": "store.example.com",
    }
    run_mock.assert_called_once()


def test_configmap_overlay_fills_fos_endpoint_from_api_when_terraform_empty(monkeypatch) -> None:
    """When terraform output lags (ignored drift / async domain), overlay uses live API."""
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setenv("REGION", "asia-northeast1")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("MODELS_BUCKET", "mlops-test-models")

    captured: dict[str, str] = {}

    def _fake_generate(*, project_id: str, models_bucket: str, meili_base_url: str, **kwargs: str):
        captured.update(kwargs)
        return {"project_id": project_id}

    with (
        patch.object(
            configmap_overlay,
            "_resolve_meili_url",
            return_value="https://meili.example.run.app",
        ),
        patch.object(
            configmap_overlay,
            "_terraform_output_map",
            return_value={
                "vector_search_index_endpoint_id": "projects/x/locations/r/indexEndpoints/123",
                "vector_search_deployed_index_id": "property_embeddings_v3",
                "vertex_feature_online_store_id": "store-a",
                "vertex_feature_view_id": "view-a",
                "vertex_feature_online_store_endpoint": "",
            },
        ),
        patch.object(
            configmap_overlay,
            "_feature_online_store_public_domain_from_api",
            return_value="123.asia-northeast1-999.featurestore.vertexai.goog",
        ),
        patch.object(configmap_overlay, "generate_configmap_data", side_effect=_fake_generate),
        patch.object(configmap_overlay, "render_configmap_yaml", return_value="apiVersion: v1\n"),
        patch.object(
            subprocess,
            "run",
            return_value=subprocess.CompletedProcess(["kubectl"], returncode=0),
        ),
    ):
        assert configmap_overlay.main() == 0

    assert captured["vertex_feature_online_store_endpoint"] == (
        "123.asia-northeast1-999.featurestore.vertexai.goog"
    )


def test_local_boot_contract_does_not_require_adc_when_search_disabled(monkeypatch) -> None:
    settings = ApiSettings(
        project_id="mlops-test",
        enable_search=False,
        enable_rerank=False,
    )

    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("local boot contract must not touch external GCP clients")

    monkeypatch.setattr(ContainerBuilder, "_bigquery", _forbidden)
    monkeypatch.setattr("app.container.infra.PubSubPublisher", _forbidden)
    monkeypatch.setattr("app.container.infra.PubSubRankingLogPublisher", _forbidden)
    monkeypatch.setattr("app.container.infra.PubSubFeedbackRecorder", _forbidden)

    container = ContainerBuilder(settings).build()

    assert container.candidate_retriever is None
    assert container.encoder_client is None
    assert container.feature_fetcher is None
    assert container.retrain_trigger_publisher is None
    assert isinstance(container.retrain_queries, NoopRetrainQueries)
    assert isinstance(container.data_catalog_service._reader, NoopDataCatalogReader)
    assert isinstance(container.ranking_log_publisher, NoopRankingLogPublisher)
    assert isinstance(container.feedback_recorder, NoopFeedbackRecorder)


def test_run_all_core_recipe_pins_canonical_validation_path() -> None:
    makefile = _read("Makefile")
    expected_lines = [
        "$(MAKE) check-layers",
        "$(MAKE) seed-test",
        "$(MAKE) sync-meili",
        "$(MAKE) ops-train-now",
        "$(MAKE) ops-train-wait",
        "$(MAKE) ops-livez",
        "$(MAKE) ops-search",
        "$(MAKE) ops-search-components",
        "$(MAKE) ops-vertex-vector-search-smoke",
        "$(MAKE) ops-vertex-feature-group",
        "$(MAKE) ops-feedback",
        "$(MAKE) ops-ranking",
        "$(MAKE) ops-label-seed",
        "$(MAKE) ops-daily",
        "$(MAKE) ops-accuracy-report",
    ]
    positions = [makefile.index(line) for line in expected_lines]
    assert positions == sorted(positions), (
        "run-all-core drifted from the canonical validation order"
    )
    assert "verify-all: ## Alias of run-all-core" in makefile
    assert "$(MAKE) run-all-core" in makefile


def test_wait_for_deployed_index_absent_is_idempotent_on_resume() -> None:
    """**Resume idempotency 契約** (2026-05-03 追加): partial deploy-all 失敗からの
    再開時、既に `READY` (indexSyncTime あり) な DeployedIndex があれば
    `wait_for_deployed_index_absent` は即 return する。

    過去事故: deploy-all step 6 で Composer API 未有効化により失敗 → 再開時に
    既デプロイ済 v2 が「absent になるのを待ち続ける」15 min timeout で fail。
    本契約は『absent OR ready』の両方を early-exit safe state として pin する。"""
    vertex_cleanup_py = _read("scripts/infra/vertex_cleanup.py")
    assert "def deployed_index_state(" in vertex_cleanup_py, (
        "deployed_index_state() must classify lifecycle (absent / ready / transitional)"
    )
    assert '"ready"' in vertex_cleanup_py and '"transitional"' in vertex_cleanup_py
    assert 'state in ("absent", "ready")' in vertex_cleanup_py, (
        "wait_for_deployed_index_absent must early-exit on both 'absent' AND 'ready' "
        "(resume scenario after partial deploy-all failure)"
    )


def test_deploy_all_waits_vertex_feature_store_and_retries_stage1_on_409() -> None:
    """Pin destroy→deploy 409 対策: list API 待ち + stage1 apply 再試行。"""
    deploy_py = _read("scripts/setup/deploy_all.py")
    stage_py = _read("scripts/infra/terraform_stage_apply.py")
    assert "wait_until_feature_store_names_released" in deploy_py
    assert "terraform_apply_stage1_with_retries" in deploy_py
    assert "terraform_apply_stage1_with_retries" in stage_py


def test_makefile_run_all_core_targets_all_exist() -> None:
    """`make run-all-core` recipe が `$(MAKE) <target>` で呼ぶ全 target が
    Makefile に実在 (typo / drift で recipe が誤った target を呼ぶ事故を防ぐ)。"""
    makefile = _read("Makefile")
    run_all_core_match = re.search(
        r"^run-all-core:.*?(?=^\S|^$)",
        makefile,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert run_all_core_match is not None, "run-all-core target not found in Makefile"
    recipe = run_all_core_match.group(0)
    invoked = re.findall(r"\$\(MAKE\)\s+([\w-]+)", recipe)
    assert invoked, "run-all-core recipe contains no $(MAKE) ... invocations"

    for target in invoked:
        target_pattern = re.compile(rf"^{re.escape(target)}:", re.MULTILINE)
        assert target_pattern.search(makefile), (
            f"run-all-core invokes '$(MAKE) {target}' but no '{target}:' rule found in Makefile"
        )
