"""Phase 7 workflow contract — docs canonical wording + cost estimate.

Pin docs/01 §3 canonical wording ("Phase 7 で本実装、後方派生で Phase 6 へ
引き算")、runbook §1.4-bis cost estimate (¥870-1,200 / 3h、当日 destroy 前提)、
implementation catalog の test inventory 整合。

過去事故: ¥9,000 padding ミス再発防止の contract。
"""

from __future__ import annotations

from tests.integration.workflow.conftest import read_repo_file as _read


def test_canonical_docs_describe_workflow_contract_goals() -> None:
    spec = _read("docs/architecture/01_仕様と設計.md")
    validation = _read("docs/runbook/04_検証.md")
    operations = _read("docs/runbook/05_運用.md")
    catalog = _read("docs/architecture/03_実装カタログ.md")

    for required in (
        "## 8. Workflow Contract が守るべきゴール",
        "G-W1. PDCA は `deploy-all -> run-all -> destroy-all` の 1 本線で完結する",
        "G-W4. canonical serving path を検証本線に含める",
        "FastAPI boot / import / `/livez` 200 は ADC なし local でも成立する",
    ):
        assert required in spec, f"spec lost workflow contract requirement: {required}"

    for required in (
        "G3 | **3 種コンポーネント (load-bearing)**",
        "G4 | **canonical semantic / feature path**",
        "make ops-vertex-vector-search-smoke",
        "scripts.ops.vertex.feature_group",
    ):
        assert required in validation, f"validation guide lost canonical gate: {required}"

    for required in (
        "## 1. PDCA メインフロー (`make deploy-all` → `make run-all` → `make destroy-all`)",
        "make run-all           # = run-all-core + リアルタイム監視 (ops-run-all-monitor)",
        "ops-vertex-vector-search-smoke",
        "ops-vertex-feature-group",
    ):
        assert required in operations, (
            f"operations guide drifted from workflow contract: {required}"
        )

    for required in (
        "tests/integration/workflow/",
        "tests/e2e/",
        "setup/deploy_all.py",
        "ops/vertex/{models_list,pipeline_status,vector_search,feature_group,monitoring,explain}.py",
    ):
        assert required in catalog, (
            f"implementation catalog drifted from workflow/test inventory: {required}"
        )


def test_composer_canonical_doc_section_exists() -> None:
    """docs/01 §3 が「Phase 7 で本実装、後方派生で Phase 6 へ引き算」の wording で
    canonical 起点を宣言していること (Stage 1.1 docs rewrite 結果 pin)。"""
    spec = _read("docs/architecture/01_仕様と設計.md")
    for required in (
        "## 3. Cloud Composer の位置づけ (Phase 7 で本実装、後方派生で Phase 6 へ引き算)",
        "**Phase 7 で本線オーケストレーターとして本実装**",
        "Vertex `PipelineJobSchedule` → **完全撤去**",
        "### 3.6 Phase 7 (= canonical) / 引き算で派生する Phase 6 で禁止する状態",
    ):
        assert required in spec, f"docs/01 §3 lost canonical Composer wording: {required!r}"


def test_cost_estimate_documented_in_runbook() -> None:
    """Stage 3 コスト見積もり (3h 学習 1 回想定) が runbook §1.4-bis に明記
    されていること — 過去の ¥9,000 padding ミス再発防止の contract。

    user authoritative wording (2026-05-02 終端) を pin: 3h cycle ¥870-1,200 +
    Composer なし時 ¥570-900 + 常駐系 vs 従量系の分解 + 当日 destroy 前提 +
    destroy 漏れリスク 24h / 1 週間 / 月放置。
    """
    runbook = _read("docs/runbook/05_運用.md")
    assert "### 1.4-bis Composer / Phase 7 フル構成のコスト見積もり" in runbook
    assert "¥870-1,200" in runbook, (
        "runbook must pin Phase 7 full 3h cycle cost as ~¥870-1,200 (user authoritative)"
    )
    assert "¥570-900" in runbook, (
        "runbook must document the without-Composer alt cost ~¥570-900 / 3h"
    )
    assert "常駐系" in runbook and "従量系" in runbook, (
        "runbook must split cost into 常駐系 vs 従量系"
    )
    assert "当日 destroy 前提" in runbook, (
        "runbook must explicitly state 'same-day destroy' contract"
    )
    assert "destroy 漏れリスク" in runbook, (
        "runbook must document destroy-leak risk (the real failure mode)"
    )
    for leak_marker in ("24h 放置", "1 週間放置", "月放置"):
        assert leak_marker in runbook, (
            f"runbook must enumerate destroy-leak scenarios including {leak_marker}"
        )
