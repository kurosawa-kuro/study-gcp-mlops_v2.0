"""End-to-end provisioning + rollout in one shot. Calls (in order):

1. `tf_bootstrap` — enable APIs + create tfstate bucket (idempotent)
2. `tf_init` — terraform init with bucket preflight
3. `recover_wif` — undelete + import WIF pool/provider if a previous
   `make destroy-all` left them soft-deleted (GCP keeps WIF resources for
   30 days after delete; recreating with the same ID otherwise hits HTTP
   409 "already exists"). Implementation lives in
   `scripts/setup/recover_wif.py` so the recovery is testable / reusable.
4. `sync_dataform` — regenerate pipeline/data_job/dataform/workflow_settings.yaml
5. `tf_plan` — terraform plan -out=tfplan (using setting.yaml defaults)
6. `terraform apply -auto-approve` — apply infra in two stages
7. `seed-lgbm-model` — `gs://<project>-models/lgbm/latest/model.bst` に
   合成 LightGBM ranker を seed (Phase 7 Run 5: tf-apply 直後の bucket は空で、
   step 10 で apply される `property-reranker` InferenceService の
   storage-initializer init container が ``RuntimeError: Failed to fetch
   model. No model found in gs://...`` で CrashLoopBackOff に陥る)。
8. `seed-test` — `feature_mart.property_features_daily` など smoke に必要な
   最小 row を seed。Feature View manual sync の source row をここで作る。
9. `sync-meili` — `feature_mart.properties_cleaned` を Meilisearch `properties`
   index へ upsert する。lexical lane が空だと `ops-search-components` が
   `lexical=0` で fail するため、canonical lexical path の一部として
   本線に組み込む。
10. `backfill-vvs` — `feature_mart.property_embeddings` から Vertex Vector Search
   index へ初回 datapoint を upsert する。endpoint / deployed index だけを作っても
   中身が空だと `ops-vertex-vector-search-smoke` が 0 neighbors で fail するため、
   Phase 7 canonical path の一部として本線に組み込む。
11. `trigger-fv-sync` — Feature Online Store / Feature View live path 向けに
   regional REST API で manual sync を起動し、完了まで poll する。
12. `apply-manifests` — `kubectl apply -k infra/manifests/` (Phase 7 Run 2:
   旧運用は手で `make apply-manifests` を叩く前提だったが、PDCA loop で
   毎回手作業を要求すると `destroy-all → deploy-all` が成立しない)。
13. `overlay-configmap` — search-api ConfigMap の `meili_base_url`
   placeholder を実 URL で上書き。実装は `scripts/deploy/configmap_overlay.py`
   で、ConfigMap schema は `scripts/lib/config.py` に集約 (Phase 7 W2-5 で
   `_run_overlay_configmap` と `sync_configmap.py` が独立にキー列を手書き
   していて drift した教訓 — 構造的に防止)。
14. `deploy/api_gke` — Cloud Build + kubectl rollout search-api。

Idempotent — re-running on an already-provisioned project applies a zero-diff
plan and rolls a fresh search-api image revision. Costs accrue from the
moment infra is created. See CLAUDE.md non-negotiables.

設計方針 (Phase 7 W3 リファクタ):
- 本ファイルは **orchestrator のみ**。各 step の business logic は
  sibling module (`scripts/{ci,deploy,setup}/<step>.py`) または
  topical module (`scripts/{lib,infra}/`) に置く。
- **Terraform**: stage1 の target 集合・409 リトライ・state lock 吸収は
  ``scripts/infra/terraform_stage_apply.py`` と ``scripts/infra/terraform_lock.py``
  に集約 (このファイルにロジックを再増殖させない)。
- _run_* は対応 module の `main()` を呼ぶだけの thin wrapper にする
  (drift 源にならないように)。
"""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts._common import cloud_run_url, env, run, terraform_var_args
from scripts.ci.sync_dataform import main as sync_dataform_main
from scripts.deploy.api_gke import main as deploy_api_main
from scripts.deploy.composer_deploy_dags import main as composer_deploy_dags_main
from scripts.deploy.configmap_overlay import main as overlay_configmap_main
from scripts.deploy.seed_lgbm_model import main as seed_lgbm_main
from scripts.infra.feature_view_sync import main as feature_view_sync_main
from scripts.infra.kubectl_context import ensure as ensure_kubectl_context
from scripts.infra.kubectl_context import wait_until_api_ready
from scripts.infra.state_recovery import recover_orphan_gcp_resources
from scripts.infra.terraform_lock import run_terraform_streaming_with_lock_retry
from scripts.infra.terraform_stage_apply import (
    TF_APPLY_STAGE1_TARGETS,
    terraform_apply_stage1_with_retries,
)
from scripts.infra.vertex_cleanup import wait_for_deployed_index_absent
from scripts.infra.vertex_feature_store_wait import wait_until_feature_store_names_released
from scripts.infra.vertex_import import import_persistent_vvs_resources
from scripts.lib.gcp_resources import GKE_CLUSTER_NAME_DEFAULT, MEILI_SERVICE_NAME_DEFAULT
from scripts.ops.sync_meili import run as sync_meili_run
from scripts.setup.backfill_vector_search_index import main as backfill_vector_search_main
from scripts.setup.recover_wif import main as recover_wif_main
from scripts.setup.seed_minimal import main as seed_minimal_main
from scripts.setup.tf_bootstrap import main as tf_bootstrap_main
from scripts.setup.tf_init import main as tf_init_main
from scripts.setup.tf_plan import main as tf_plan_main

INFRA = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "environments" / "dev"
MANIFESTS = Path(__file__).resolve().parents[2] / "infra" / "manifests"

# Overall start time; per-step timing relates elapsed time to the wall-clock
# position in the deploy-all sequence so operators can see WHICH step is slow
# when a rollout hangs (e.g. Cloud Build wait dominating step 7).
_DEPLOY_ALL_STARTED_AT: float | None = None
_STEP_STARTED_AT: float | None = None


@dataclass(frozen=True)
class DeployStep:
    number: int
    name: str
    label: str
    run: Callable[[], int]


def _step(n: int, total: int, label: str) -> None:
    global _DEPLOY_ALL_STARTED_AT, _STEP_STARTED_AT
    now = time.monotonic()
    if _DEPLOY_ALL_STARTED_AT is None:
        _DEPLOY_ALL_STARTED_AT = now
    prev_elapsed = now - _STEP_STARTED_AT if _STEP_STARTED_AT is not None else 0.0
    total_elapsed = now - _DEPLOY_ALL_STARTED_AT
    _STEP_STARTED_AT = now
    print()
    print("================================================================")
    print(f" deploy-all  step {n}/{total}: {label}")
    if n > 1:
        print(f" (prev_step_elapsed={prev_elapsed:.0f}s total_elapsed={total_elapsed:.0f}s)")
    print("================================================================")


def _step_done() -> None:
    """Emit a `step-done` line with elapsed seconds for the step just finished."""
    if _STEP_STARTED_AT is None:
        return
    elapsed = time.monotonic() - _STEP_STARTED_AT
    print(f" deploy-all  step-done elapsed={elapsed:.0f}s")


def _run_tf_bootstrap() -> int:
    return tf_bootstrap_main()


def _run_tf_init() -> int:
    return tf_init_main()


def _run_recover_wif() -> int:
    return recover_wif_main()


def _run_sync_dataform() -> int:
    return sync_dataform_main()


def _run_tf_plan() -> int:
    return tf_plan_main()


def _run_tf_apply() -> int:
    project_id = env("PROJECT_ID")
    region = env("REGION", "asia-northeast1")
    cluster_name = env("GKE_CLUSTER_NAME", GKE_CLUSTER_NAME_DEFAULT)
    deployed_index_id = env("VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID", "property_embeddings_v3")

    # 永続化アーキテクチャ (`docs/tasks/TASKS_ROADMAP.md §4.9`、2026-05-03):
    # 前回 destroy-all で `module.vector_search` の Index / Endpoint を **state rm
    # + GCP 残置** している場合がある。tf-apply 前に既存 GCP resource を state へ
    # import することで、terraform plan は「Index/Endpoint = no-op、deployed_index
    # のみ create」となり、Index build 5-15 min + Endpoint create + DNS propagation
    # を省略して deploy-all 27 min → 10-15 min に短縮できる。
    print(f"==> tf-apply pre-step: VVS Index/Endpoint state import check (region={region})")
    imported = import_persistent_vvs_resources(
        INFRA,
        project_id,
        region,
        terraform_var_args=list(terraform_var_args("GITHUB_REPO", "ONCALL_EMAIL")),
    )
    if imported:
        print(f"==> {imported} addr imported into state — terraform plan で no-op 扱いになる")

    # 2026-05-03 incident postmortem (`docs/tasks/TASKS_ROADMAP.md §4.10`):
    # 緊急 cleanup で `gcloud delete --async` で Composer/GKE/Cloud Run しか消さなかった
    # 後に runbook §1.4-emergency の `state rm` で全 state を消すと、IAM SA / BQ /
    # Pub/Sub / Cloud Function / Eventarc / Cloud Run (Meilisearch) などが GCP 残置
    # かつ state 不在で、tf-apply stage1 が `Error: alreadyExists` で fail する。
    # IAM SA は soft-delete 30 日 window があるため gcloud delete → 即 terraform create
    # も fail する罠あり。本 helper は existing GCP resources を type ごとに list して
    # state へ import で吸収 (idempotent、何度叩いてもそれ以上 import しない)。
    print(f"==> tf-apply pre-step: orphan GCP resource state recovery (region={region})")
    recovered = recover_orphan_gcp_resources(
        INFRA,
        project_id,
        region,
        terraform_var_args=list(terraform_var_args("GITHUB_REPO", "ONCALL_EMAIL")),
    )
    if recovered:
        print(f"==> {recovered} orphan resource(s) imported — tf-apply 'alreadyExists' fail 回避")

    wait_for_deployed_index_absent(project_id, region, deployed_index_id)

    # destroy-all → deploy-all の短間隔では Vertex Feature Group / Feature Online Store が
    # GCP 側で非同期削除中のまま同名 create が走り HTTP 409 になる。list API で名前解放を待つ。
    vertex_region = env("VERTEX_LOCATION") or region
    wait_until_feature_store_names_released(project_id, vertex_region)

    stage1_args = [
        "terraform",
        f"-chdir={INFRA}",
        "apply",
        "-auto-approve",
        *terraform_var_args("GITHUB_REPO", "ONCALL_EMAIL"),
        *[f"-target={target}" for target in TF_APPLY_STAGE1_TARGETS],
    ]
    print(
        "==> terraform apply stage1 (core infra before kube provider resources): "
        + ", ".join(TF_APPLY_STAGE1_TARGETS)
    )
    terraform_apply_stage1_with_retries(stage1_args, chdir_infra=INFRA)

    print(f"==> refresh kubeconfig + wait for cluster API: cluster={cluster_name} region={region}")
    ensure_kubectl_context()
    wait_until_api_ready()

    print("==> terraform apply stage2 (full graph including module.kserve)")
    run_terraform_streaming_with_lock_retry(
        [
            "terraform",
            f"-chdir={INFRA}",
            "apply",
            "-auto-approve",
            *terraform_var_args("GITHUB_REPO", "ONCALL_EMAIL"),
        ],
        chdir_infra=INFRA,
    )
    return 0


def _run_seed_lgbm_model() -> int:
    return seed_lgbm_main()


def _run_seed_test() -> int:
    return seed_minimal_main()


def _run_sync_meili() -> int:
    project_id = env("PROJECT_ID")
    meili_service = env("MEILI_SERVICE", MEILI_SERVICE_NAME_DEFAULT)
    meili_base_url = cloud_run_url(meili_service)
    identity_token = run(["gcloud", "auth", "print-identity-token"], capture=True).stdout or ""
    api_key = (
        run(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                "latest",
                "--secret=meili-master-key",
                f"--project={project_id}",
            ],
            capture=True,
        ).stdout
        or ""
    )
    previous_token = os.environ.get("MEILI_PRESIGNED_ID_TOKEN")
    os.environ["MEILI_PRESIGNED_ID_TOKEN"] = identity_token.strip()
    try:
        synced = sync_meili_run(
            [
                f"--project-id={project_id}",
                f"--meili-base-url={meili_base_url}",
                "--require-identity-token",
                f"--api-key={api_key.strip()}",
            ]
        )
    finally:
        if previous_token is None:
            os.environ.pop("MEILI_PRESIGNED_ID_TOKEN", None)
        else:
            os.environ["MEILI_PRESIGNED_ID_TOKEN"] = previous_token
    return 0 if synced >= 0 else 1


def _run_trigger_feature_view_sync() -> int:
    return feature_view_sync_main()


def _run_backfill_vvs() -> int:
    return backfill_vector_search_main(["--apply"])


def _run_apply_manifests() -> int:
    """`kubectl apply -k infra/manifests/` against the freshly-provisioned cluster.

    Phase 7 Run 2 まで `infra/manifests/README.md §デプロイ` は「Terraform apply
    後に make apply-manifests を手で叩く」運用だった。PDCA dev loop
    (`destroy-all → deploy-all → run-all`) ではこの手作業が成立しないため、
    deploy-all に組み込んで一発で cluster ワークロードを展開する。
    試行錯誤目的の手 apply は引き続き ``make apply-manifests`` で可能。
    """
    ensure_kubectl_context()
    print(f"==> kubectl apply -k {MANIFESTS}")
    run(["kubectl", "apply", "-k", str(MANIFESTS)])
    return 0


def _run_overlay_configmap() -> int:
    return overlay_configmap_main()


def _run_composer_deploy_dags() -> int:
    return composer_deploy_dags_main()


def _run_deploy_api() -> int:
    return deploy_api_main()


def _steps() -> list[DeployStep]:
    return [
        DeployStep(
            1,
            "tf-bootstrap",
            "tf-bootstrap (enable APIs + tfstate bucket, idempotent)",
            _run_tf_bootstrap,
        ),
        DeployStep(2, "tf-init", "tf-init (preflight + terraform init)", _run_tf_init),
        DeployStep(
            3,
            "recover-wif",
            "recover WIF pool/provider if soft-deleted (PDCA loop safety)",
            _run_recover_wif,
        ),
        DeployStep(
            4,
            "sync-dataform",
            "sync-dataform-config (regenerate workflow_settings.yaml)",
            _run_sync_dataform,
        ),
        DeployStep(5, "tf-plan", "tf-plan (saves infra/tfplan)", _run_tf_plan),
        DeployStep(
            6, "tf-apply", "terraform apply staged (core -> kube-ready -> full)", _run_tf_apply
        ),
        DeployStep(
            7,
            "seed-lgbm-model",
            "seed gs://<project>-models/lgbm/latest/model.bst (reranker bootstrap)",
            _run_seed_lgbm_model,
        ),
        DeployStep(
            8,
            "seed-test",
            "seed-test (populate feature_mart tables for smoke + Feature View sync)",
            _run_seed_test,
        ),
        DeployStep(
            9,
            "sync-meili",
            "sync Meilisearch from feature_mart.properties_cleaned (canonical lexical path)",
            _run_sync_meili,
        ),
        DeployStep(
            10,
            "backfill-vvs",
            "backfill VVS from feature_mart.property_embeddings (canonical semantic path)",
            _run_backfill_vvs,
        ),
        DeployStep(
            11,
            "trigger-fv-sync",
            "trigger Feature View sync and wait for completion (FOS live path)",
            _run_trigger_feature_view_sync,
        ),
        DeployStep(
            12,
            "apply-manifests",
            "kubectl apply -k infra/manifests/ (Gateway / Deployment / ISVC / policies)",
            _run_apply_manifests,
        ),
        DeployStep(
            13,
            "overlay-configmap",
            "overlay search-api-config (resolve real meili_base_url + VVS/FOS outputs)",
            _run_overlay_configmap,
        ),
        DeployStep(
            14,
            "composer-deploy-dags",
            "upload pipeline/dags/*.py to Composer DAG GCS bucket (Phase 7 W2-4)",
            _run_composer_deploy_dags,
        ),
        DeployStep(
            15,
            "deploy-api",
            "deploy-api (Cloud Build + kubectl rollout search-api)",
            _run_deploy_api,
        ),
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Phase 7 deploy-all flow with optional step slicing."
    )
    parser.add_argument(
        "--from-step",
        default="1",
        help="Start from this step number or name (e.g. 4, sync-dataform, tf-apply).",
    )
    parser.add_argument(
        "--to-step",
        default="15",
        help="Stop after this step number or name (e.g. 9, sync-meili, deploy-api).",
    )
    return parser.parse_args()


def _resolve_step_ref(ref: str, steps: list[DeployStep]) -> int:
    raw = ref.strip()
    if raw.isdigit():
        step_no = int(raw)
        if any(step.number == step_no for step in steps):
            return step_no
    lowered = raw.lower()
    for step in steps:
        if lowered == step.name:
            return step.number
    valid = ", ".join([str(step.number) for step in steps] + [step.name for step in steps])
    raise SystemExit(f"[error] unknown step {ref!r}. valid values: {valid}")


def main() -> int:
    global _DEPLOY_ALL_STARTED_AT, _STEP_STARTED_AT
    _DEPLOY_ALL_STARTED_AT = None
    _STEP_STARTED_AT = None

    args = _parse_args()
    steps = _steps()
    total = len(steps)
    from_step = _resolve_step_ref(args.from_step, steps)
    to_step = _resolve_step_ref(args.to_step, steps)
    if from_step > to_step:
        raise SystemExit(f"[error] --from-step ({from_step}) must be <= --to-step ({to_step})")

    selected = [step for step in steps if from_step <= step.number <= to_step]
    print(
        f"==> deploy-all selection: from_step={from_step} to_step={to_step} "
        f"steps={[step.name for step in selected]}"
    )

    current_step: DeployStep | None = None
    try:
        for step in selected:
            current_step = step
            _step(step.number, total, step.label)
            rc = step.run()
            if rc != 0:
                print(f"==> deploy-all FAILED at step {step.number} ({step.name}) — see logs above")
                return rc
            _step_done()
    except BaseException:
        if current_step is not None:
            print(
                f"==> deploy-all FAILED at step {current_step.number} ({current_step.name}) "
                "— see traceback above"
            )
        raise

    if _DEPLOY_ALL_STARTED_AT is not None:
        total_elapsed = time.monotonic() - _DEPLOY_ALL_STARTED_AT
        print()
        print(f"==> deploy-all complete. total_elapsed={total_elapsed:.0f}s")
    else:
        print()
        print("==> deploy-all complete.")
    print("    Verify with: make ops-livez && make ops-api-url")
    print("    Pipeline submit is separate: make ops-train-now")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
