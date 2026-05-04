"""Phase 7 workflow contract — `make destroy-all` teardown + reproducibility.

Pin the destroy ordering, the Vertex Endpoint deployed-model undeploy, the
Vector Search deployed-index undeploy guard (PDCA reproducibility),
BigQuery `deletion_protection` flip, GCS bucket `force_destroy` wipe, and
the WIF pool soft-delete recovery.
"""

from __future__ import annotations

from scripts.setup import destroy_all
from tests.integration.workflow.conftest import read_repo_file as _read


def test_destroy_all_keeps_pdca_reproducibility_guards() -> None:
    assert "module.gke.google_container_cluster.hybrid_search" in destroy_all.PROTECTED_TARGETS
    assert "module.data.google_bigquery_table.property_features_daily" in (
        destroy_all.PROTECTED_TARGETS
    )
    assert destroy_all.KSERVE_MODULE_TARGET == "module.kserve"

    source = _read("scripts/setup/destroy_all.py")
    assert "state list is empty — nothing to destroy" in source
    assert "seed-test-clean" in source
    assert "undeploy Vertex endpoint deployed_models" in source
    assert "terraform destroy -target=module.kserve" in source
    assert "terraform destroy -auto-approve (本体)" in source


def test_destroy_all_destroy_apply_symmetry() -> None:
    """**destroy-all ↔ deploy-all 対称性**: deploy-all が立てる主要 module は
    destroy-all で `terraform destroy -auto-approve` の連鎖で消える契約。

    KServe Helm provider race を回避する `KSERVE_MODULE_TARGET` 先行 destroy が
    維持されていることを pin。
    """
    destroy_all_py = _read("scripts/setup/destroy_all.py")
    stage_apply_py = _read("scripts/infra/terraform_stage_apply.py")

    assert 'KSERVE_MODULE_TARGET = "module.kserve"' in destroy_all_py
    assert "terraform destroy -target=module.kserve" in destroy_all_py

    for required_module in (
        "module.iam",
        "module.data",
        "module.vector_search",
        "module.vertex",
        "module.gke",
        "module.composer",
    ):
        assert required_module in stage_apply_py, (
            f"deploy-all stage1 targets must include {required_module}"
        )


def test_destroy_all_undeploys_vertex_endpoint_models_before_destroy() -> None:
    """Vertex AI Endpoint の `deployedModels` が undeploy 済になってから
    `terraform destroy` する契約。

    Endpoint が deployed_model を持つ状態で destroy すると HTTP 400
    `Endpoint has deployed or being-deployed DeployedModel(s)`、手動 cleanup
    で 5-15 min ロス。"""
    destroy_all_py = _read("scripts/setup/destroy_all.py")
    assert "vertex_cleanup.undeploy_all_endpoint_shells" in destroy_all_py


def test_destroy_all_proactively_undeploys_stale_vvs_indexes() -> None:
    """**PDCA reproducibility 契約** (2026-05-02 追加): `destroy-all` は
    Vector Search の deployed index を能動的に undeploy する。

    過去事故: 前 PDCA cycle が deployed index を残したまま終わると、次の
    `make deploy-all` step 6 で 15 min wait timeout で fail。`deploy-all` 側
    `wait_for_deployed_index_absent` は wait しかしないため、destroy 側に
    proactive undeploy を入れる責任がある。"""
    destroy_all_py = _read("scripts/setup/destroy_all.py")
    vertex_cleanup_py = _read("scripts/infra/vertex_cleanup.py")

    assert "def undeploy_all_vvs_deployed_indexes(" in vertex_cleanup_py
    assert '"undeploy-index"' in vertex_cleanup_py, (
        "must invoke 'gcloud ai index-endpoints undeploy-index' (not just describe / wait)"
    )
    assert "vertex_cleanup.undeploy_all_vvs_deployed_indexes" in destroy_all_py


def test_destroy_all_flips_bq_deletion_protection_before_destroy() -> None:
    """BigQuery table の `deletion_protection=true` を destroy 前に **state-flip**
    する契約 (Terraform default で destroy 拒否される)。"""
    destroy_all_py = _read("scripts/setup/destroy_all.py")
    data_tf = _read("infra/terraform/modules/data/main.tf")

    assert "PROTECTED_TARGETS" in destroy_all_py
    assert "enable_deletion_protection=false" in destroy_all_py

    declared_tables = __import__("re").findall(
        r'resource "google_bigquery_table" "(\w+)"',
        data_tf,
    )
    for table_resource in declared_tables:
        assert table_resource in destroy_all_py or "deletion_protection = false" in data_tf, (
            f"google_bigquery_table.{table_resource} should appear in destroy_all.py "
            "PROTECTED_TARGETS (BQ default deletion_protection=true)"
        )


def test_destroy_all_force_destroys_blocking_gcs_buckets() -> None:
    """`force_destroy=false` な GCS bucket が中身を持つと destroy が止まる。
    `gcloud storage rm --recursive` で wipe してから destroy する契約。"""
    destroy_all_py = _read("scripts/setup/destroy_all.py")
    assert "gcs_cleanup" in destroy_all_py
    assert "wipe_all_terraform_managed_buckets" in destroy_all_py


def test_recover_wif_handles_soft_delete_undelete() -> None:
    """destroy → 即 deploy で WIF pool が soft-delete (30 日保持) のため
    409 conflict になるのを undelete で recover する契約。

    自動化なしだと 30 日間 WIF が使えず destroy-all 後の deploy 完全 block。"""
    deploy_all_py = _read("scripts/setup/deploy_all.py")
    recover_wif_py = _read("scripts/setup/recover_wif.py")

    assert "recover_wif" in deploy_all_py, "deploy-all must call recover_wif before terraform apply"
    assert "undelete" in recover_wif_py.lower(), (
        "recover_wif.py must handle WIF pool undelete (30-day soft-delete window)"
    )


def test_destroy_all_persists_vvs_index_and_endpoint() -> None:
    """**VVS 永続化契約** (2026-05-03、`docs/tasks/TASKS_ROADMAP.md §4.9`):
    Vertex Vector Search の Index と Index Endpoint は **無料で残せる** (replica 0
    の Endpoint と未 deploy の Index は課金されない)。Index build に 5-15 min、
    Endpoint 作成に数分 + DNS propagation がかかるため、PDCA cycle ごとに作り
    直すと deploy-all 27 min → 10-15 min の短縮効果が出ない。

    実装パターン: `lifecycle.prevent_destroy = true` は依存閉包で touch される
    resource (e.g. deployed_index → Endpoint) を block できず、`Instance cannot
    be destroyed` で全 destroy が止まる事故を 2026-05-03 に観測したため不採用。
    代わりに **state rm + GCP 残置** + 次回 deploy-all で `terraform import` で
    state 復元する pattern に変更。

    本契約は以下を pin する:
    1. `module.vector_search` の Index / Endpoint に `prevent_destroy` を入れない
       (誤った設計判断の再導入を block)
    2. `destroy_all.py` で `PERSISTENT_VVS_RESOURCES` を state rm する
    3. `deploy_all.py` で `import_persistent_vvs_resources` を呼ぶ
    """
    main_tf = _read("infra/terraform/modules/vector_search/main.tf")
    destroy_all_py = _read("scripts/setup/destroy_all.py")
    deploy_all_py = _read("scripts/setup/deploy_all.py")
    vertex_import_py = _read("scripts/infra/vertex_import.py")

    # main.tf — Index / Endpoint には prevent_destroy を入れない (state rm pattern)
    # コメント内の説明文の `prevent_destroy = true` は誤検知させない (lifecycle block のみ確認)
    import re as _re

    for lifecycle_block in _re.findall(r"lifecycle\s*\{[^}]*\}", main_tf, flags=_re.DOTALL):
        assert "prevent_destroy = true" not in lifecycle_block, (
            "vector_search/main.tf lifecycle block must NOT use prevent_destroy = true "
            "(2026-05-03 incident: 依存閉包の destroy で block されて全 destroy が止まる)"
        )

    # destroy_all.py の persistent list + state rm 呼出し
    assert "PERSISTENT_VVS_RESOURCES" in destroy_all_py
    assert '"module.vector_search.google_vertex_ai_index.property_embeddings"' in destroy_all_py
    assert (
        '"module.vector_search.google_vertex_ai_index_endpoint.property_embeddings"'
        in destroy_all_py
    )
    assert "state rm 永続化 VVS" in destroy_all_py, (
        "destroy_all must `state rm` PERSISTENT_VVS_RESOURCES (= GCP 残置 / state 外し)"
    )
    assert "state_rm(INFRA, addr)" in destroy_all_py

    # deploy_all.py の import 呼出し
    assert "import_persistent_vvs_resources" in deploy_all_py, (
        "deploy_all must invoke import_persistent_vvs_resources before tf-apply"
    )

    # vertex_import.py が gcloud で existing resource を確認 + terraform import を発行
    assert "def import_persistent_vvs_resources(" in vertex_import_py
    assert '"terraform"' in vertex_import_py and '"import"' in vertex_import_py
    assert "gcloud" in vertex_import_py and "ai" in vertex_import_py


def test_no_vertex_pipeline_job_schedule_resource_in_terraform() -> None:
    """カニバリ NG: Vertex `PipelineJobSchedule` は Phase 7 で完全撤去
    (docs/01 §3.6)。Composer DAG schedule との二重起動を防ぐ。"""
    from tests.integration.workflow.conftest import REPO_ROOT

    tf_dir = REPO_ROOT / "infra" / "terraform"
    forbidden_patterns = ("google_vertex_ai_pipeline_job_schedule", "PipelineJobSchedule")
    for tf_file in tf_dir.rglob("*.tf"):
        text = tf_file.read_text(encoding="utf-8")
        for forbidden in forbidden_patterns:
            assert forbidden not in text, (
                f"{tf_file.relative_to(REPO_ROOT)} contains forbidden {forbidden!r} "
                "(Phase 7 W2-4 で撤去済、§3.6 カニバリ NG で再導入禁止)"
            )


# ---------------------------------------------------------------------------
# 2026-05-03 incident postmortem — destroy-all の hang 事故から学んだ契約。
# 既存 9 件は構造的 guard (PROTECTED_TARGETS / 文字列存在 / 対称性) のみで、
# 「destroy-all が実際に詰まったときの recovery 経路」は契約として書かれて
# いなかった。本セクションはその gap を埋める。
# ---------------------------------------------------------------------------


def test_runbook_documents_emergency_kill_switch_for_composer_gke_cloudrun() -> None:
    """**緊急 kill switch 契約** (2026-05-03 incident、`docs/tasks/TASKS_ROADMAP.md §4.9`):
    `make destroy-all` が hang した時の最終手段として、Composer / GKE / Cloud Run
    の主要課金 resource を `gcloud delete --async` で直接消す経路を runbook に
    明記する契約。

    過去事故: `lifecycle.prevent_destroy = true` で `[6/6]` 本体 destroy が hang
    し、Composer + GKE + Cloud Run + FOS が課金継続。escape hatch が runbook に
    無かったため、user が手動で `gcloud composer environments delete --async` 等
    を試行錯誤で発見する状況になった。本契約は「次に同じ事態が起きた時に runbook
    だけ見れば 1 分で主要課金を止められる」ことを保証する。"""
    runbook = _read("docs/runbook/05_運用.md")

    # 緊急節の存在
    assert "1.4-emergency" in runbook or "緊急 kill switch" in runbook, (
        "runbook 05_運用.md must document the emergency kill-switch path "
        "(see docs/tasks/TASKS_ROADMAP.md §4.9 lessons learned)"
    )
    # 主要課金 3 経路のコマンドが揃っていること
    assert "gcloud composer environments delete" in runbook
    assert "gcloud container clusters delete" in runbook
    assert "gcloud run services delete" in runbook
    # `--async` を使う (sync で待つと shell が固まり deploy-all を再走できなくなる)
    assert "--async" in runbook, (
        "emergency kill switch must use --async — sync delete blocks the shell"
    )


def test_runbook_documents_orphan_state_cleanup_after_emergency_delete() -> None:
    """**緊急 cleanup 後の tfstate 整合性回復契約** (2026-05-03 incident 同上):
    `gcloud delete --async` で GCP 側を直接消すと tfstate に orphan entry が残る。
    次回 `make deploy-all` が「Resource not found」で fail するのを防ぐため、
    orphan を `state rm` で消す手順が runbook に明記されている契約。

    実測: 2026-05-03 朝の `terraform state list | wc -l` で orphan 151 entries
    残置を観測。手順が docs に無いと user が自力で grep / state rm を組み立て
    なくてはならない。"""
    runbook = _read("docs/runbook/05_運用.md")

    # state list / state rm の使い方が runbook 内に記載されている
    assert "terraform" in runbook and "state list" in runbook
    assert "state rm" in runbook
    # **state-recover を先に呼ぶ** ことが runbook に書かれていること
    # (2026-05-03 後 incident 教訓: bare state rm 単独だと alreadyExists 罠を作る)
    assert "make state-recover" in runbook, (
        "runbook must instruct operators to run `make state-recover` BEFORE bare state rm "
        "(see contract test_deploy_all_invokes_state_recovery_before_tf_apply)"
    )
    # cleanup 対象 module が明示列挙されている
    assert "module.composer" in runbook
    assert "module.gke" in runbook
    assert "module.kserve" in runbook


def test_deploy_all_invokes_state_recovery_before_tf_apply() -> None:
    """**state recovery 契約** (2026-05-03 後 incident、`docs/tasks/TASKS_ROADMAP.md §4.10`):
    `runbook §1.4-emergency` の「全件 state rm」レシピは GCP 側で本当に削除された
    resources のみを対象にすべきだが、`gcloud delete --async` で Composer/GKE/Cloud Run
    しか消していない場合に全件 state rm すると、IAM SA / BQ / Pub/Sub / Cloud Function /
    Eventarc / Cloud Run (Meilisearch) などが GCP 残置 + state 不在になり、tf-apply
    stage1 で `Error: alreadyExists` が大量発生して deploy-all が止まる。

    本契約は以下を pin する:
    1. `scripts/infra/state_recovery.py` が存在し、`recover_orphan_gcp_resources` を export
    2. `scripts/setup/deploy_all.py::_run_tf_apply` が tf-apply 直前に `recover_orphan_gcp_resources` を呼ぶ
    3. `Makefile` に `make state-recover` target が存在 (CLI single-shot smoke)
    4. recovery 対象 resource type が IAM SA / BQ dataset+table / Pub/Sub topic+sub /
       Cloud Function / Eventarc / Cloud Run の 6 種を網羅
    """
    state_recovery_py = _read("scripts/infra/state_recovery.py")
    deploy_all_py = _read("scripts/setup/deploy_all.py")
    makefile = _read("Makefile")

    # 1. state_recovery.py が存在し、entrypoint を export
    assert "def recover_orphan_gcp_resources(" in state_recovery_py, (
        "state_recovery.py must export `recover_orphan_gcp_resources`"
    )
    # 2. deploy_all.py が tf-apply 前に呼ぶ
    assert "from scripts.infra.state_recovery import recover_orphan_gcp_resources" in deploy_all_py
    assert "recover_orphan_gcp_resources(" in deploy_all_py, (
        "deploy_all.py::_run_tf_apply must call recover_orphan_gcp_resources before tf-apply"
    )
    # 3. Make target
    assert "state-recover:" in makefile, "Makefile must have `state-recover` target"
    assert "scripts.infra.state_recovery" in makefile
    # 4. recovery resource types が 11 種網羅 (2026-05-03 後 incident で複数回拡張:
    # Artifact Registry / Secret Manager / Dataform repo / GCS buckets / Feature Store
    # の `alreadyExists` も実観測。Feature Store は Feature Group + Feature Online Store
    # + Feature View の 3 sub-resource を 1 helper で recover)
    for required_helper in (
        "_recover_iam_sas",
        "_recover_bq",
        "_recover_pubsub",
        "_recover_cloudfunctions",
        "_recover_eventarc",
        "_recover_cloud_run",
        "_recover_artifact_registry",
        "_recover_secret_manager",
        "_recover_dataform",
        "_recover_gcs_buckets",
        "_recover_feature_store",
    ):
        assert f"def {required_helper}(" in state_recovery_py, (
            f"state_recovery.py must implement `{required_helper}` "
            "(IAM SA / BQ / Pub/Sub / Cloud Function / Eventarc / Cloud Run / "
            "Artifact Registry / Secret Manager / Dataform / GCS buckets / "
            "Feature Store の 11 種)"
        )


def test_state_recovery_iam_sa_mapping_matches_terraform() -> None:
    """**IAM SA mapping 整合契約**: `state_recovery.IAM_SA_NAMES` は `infra/terraform/
    modules/iam/main.tf` の `google_service_account` resource label と完全一致する。

    新 SA を main.tf に追加したら本 list にも追加する責務を contract で固定。
    drift すると recovery が新 SA を import せず、`alreadyExists` で fail。
    """
    state_recovery_py = _read("scripts/infra/state_recovery.py")
    iam_main_tf = _read("infra/terraform/modules/iam/main.tf")

    import re as _re

    declared_sas = set(_re.findall(r'resource "google_service_account" "(\w+)"', iam_main_tf))
    # state_recovery.IAM_SA_NAMES tuple の中身を抽出 (multi-line tuple)
    tuple_match = _re.search(r"IAM_SA_NAMES\s*=\s*\(([^)]*)\)", state_recovery_py, flags=_re.DOTALL)
    assert tuple_match, "state_recovery.py must define IAM_SA_NAMES tuple"
    listed_sas = set(_re.findall(r'"(\w+)"', tuple_match.group(1)))
    missing = declared_sas - listed_sas
    assert not missing, (
        f"state_recovery.IAM_SA_NAMES is missing SAs declared in iam/main.tf: {sorted(missing)}. "
        "Add them to IAM_SA_NAMES so `make state-recover` can import them after orphan cleanup."
    )


def test_runbook_warns_against_bare_state_rm_without_state_recovery() -> None:
    """**runbook 警告契約** (2026-05-03 後 incident): `runbook §1.4-emergency` の
    orphan cleanup 手順に、bare `state rm` の罠 (= IAM SA など実は GCP に残っている
    resource を state から消すと、再 deploy が `alreadyExists` で fail) と、
    その回避として `make state-recover` を deploy-all 前に呼ぶ案内が明記されている契約。

    過去事故 (2026-05-03): 同じレシピで全件 state rm した結果 14 IAM SA + 4 Pub/Sub +
    3 BQ dataset + Cloud Function + Eventarc + Cloud Run が orphan 化、deploy-all が
    sa-composer の `alreadyExists` で fail。"""
    runbook = _read("docs/runbook/05_運用.md")

    # state-recover の言及
    assert "make state-recover" in runbook or "state_recovery" in runbook, (
        "runbook must reference `make state-recover` for orphan recovery"
    )
    # bare state rm の罠への警告
    assert "alreadyExists" in runbook or "soft-delete" in runbook, (
        "runbook must warn that bare `state rm` after partial gcloud delete leaves "
        "GCP resources orphan (IAM SA / BQ / Pub/Sub etc.) and tf-apply will fail with "
        "`alreadyExists`"
    )


def test_destroy_all_lessons_learned_documented_in_roadmap() -> None:
    """**lessons learned 契約** (2026-05-03 incident): `prevent_destroy` 撤回 +
    state rm pattern への移行決定が `docs/tasks/TASKS_ROADMAP.md §4.9` に
    記録されている契約。

    決定背景が docs に残っていないと、将来「Index/Endpoint を保護したい」と
    いう要件で再度 `prevent_destroy` を導入する誤った PR が出る (= 同じ事故を
    繰り返す)。本契約はその再発を block する。"""
    roadmap = _read("docs/tasks/TASKS_ROADMAP.md")

    # §4.9 の存在
    assert "§4.9" in roadmap or "### 4.9" in roadmap, (
        "TASKS_ROADMAP.md must have §4.9 (VVS persistence architecture)"
    )
    # 失敗事故 + 真因分析 + 採用方針が揃っている
    assert "Instance cannot be destroyed" in roadmap, (
        "§4.9 must reference the actual error message that triggered the redesign"
    )
    assert "prevent_destroy" in roadmap, "§4.9 must explain why prevent_destroy was abandoned"
    assert "state rm" in roadmap and "terraform import" in roadmap, (
        "§4.9 must document the replacement pattern (state rm + terraform import)"
    )
    # 別 sprint 候補 (将来 strict 化) が backlog として残っている
    assert "Stack 分離" in roadmap or "Cloud Scheduler 自動 undeploy" in roadmap, (
        "§4.9 must record stronger-protection backlog (stack split / auto-undeploy / "
        "billing alert / health check) so the lessons trigger future hardening"
    )
