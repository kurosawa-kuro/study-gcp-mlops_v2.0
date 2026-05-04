"""Shared fixtures + helpers for Phase 7 workflow contract tests.

Tests are split into themed files under `tests/integration/workflow/`:

- `test_deploy_all_contract.py` — deploy-all step sequence / ordering /
  ConfigMap overlay / run-all-core / local boot contract + Feature Store 待ち・
  stage1 409 リトライの contract pin
- `test_destroy_all_contract.py` — destroy-all teardown / PDCA reproducibility
  guards (Vertex undeploy / VVS undeploy / BQ deletion_protection flip /
  GCS force_destroy / WIF undelete)
- `test_composer_module_contract.py` — Composer Terraform module + IAM SA +
  Make targets + wiring (大物)
- `test_composer_dags_contract.py` — Composer DAG file structural validity
  (schedule / dag_id / KFP 2.16 回避 / script reference)
- `test_vertex_resources_contract.py` — Vertex Vector Search / Feature Online
  Store / 軽量 trigger 格下げ
- `test_infra_apis_contract.py` — Phase 7 module ↔ API enablement / region
  consistency / GKE 2-stage apply / manifest image lifecycle / ops-vertex-all
- `test_docs_canonical_contract.py` — docs canonical wording / cost estimate
- `test_composer_gcloud_json_contract.py` — gcloud stdout → ``[{`` JSON extraction
  + list-runs run_id parse (Composer ops incident)
- `test_vertex_pipeline_submit_contract.py` — ``resolve_project_id`` in submit/wait scripts

なぜ 1 ファイルに固めないか: 1 ファイル肥大化 (1300+ 行) でテーマ別の見通し
が悪化したため、2026-05-03 に分割。共通 helper は本 conftest に集約。
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DAGS_DIR = REPO_ROOT / "pipeline" / "dags"
COMPOSER_MODULE_DIR = REPO_ROOT / "infra" / "terraform" / "modules" / "composer"
DAG_FILES = ("daily_feature_refresh.py", "retrain_orchestration.py", "monitoring_validation.py")


def read_repo_file(rel: str) -> str:
    """Helper: read a file relative to REPO_ROOT as utf-8 text."""
    return (REPO_ROOT / rel).read_text(encoding="utf-8")
