# 02. 移行ロードマップ — 検索アプリを最新仕様へ

Phase 7 の現コードを、最新仕様 (親 [README.md](../../../../README.md) §1-§4 / 親 [docs/architecture/01_仕様と設計.md](../../../../docs/architecture/01_仕様と設計.md) / 本 phase [docs/architecture/01_仕様と設計.md](../architecture/01_仕様と設計.md)) に追従させるための移行計画。

> **2026-05-03 教育コード化方針の改訂**: コード化対象を **Phase 1 / 2 / 3 / 4 / 7** に限定。Phase 5 / 6 は **論理 Phase** (個別コード保守なし、本 Phase 7 完成版コードを参照する資料中心の Phase)。Phase 4 は **本 Phase からの引き算ではなく Phase 3 からの足し算** で独立コード化 (GCP MLOps 土台、Vertex AI 以降は含めない)。詳細は親 [`README.md` §4 コード化方針](../../../../README.md)。
>
> 本 Phase 7 は **教材コード完成版 / canonical 起点** であり、Phase 5 / 6 の技術要素 (Vertex AI Pipelines / Feature Store / Vertex Vector Search / Cloud Composer 本線 + PMLE 4 技術) を本 phase 配下に集約する。

> **方針**: **Wave 1 = 検索アプリ自体 (app / ml / pipeline コード)** を先に整える。**Wave 2 = GCP インフラ (Terraform / IAM / deploy)** はその後。Wave 3 は docs / reference architecture との整合確認のみ (コード変更なし)。
>
> Port / Adapter / DI 大枠の整理は [`docs/TASKS_ROADMAP.md`](TASKS_ROADMAP.md)、過去の制約決定は [`docs/decisions/`](../decisions/README.md) を参照。
>
> **教育コード原則**: 後方互換・legacy fallback・旧 env 名 alias・旧 UI redirect・使われない shell resource は残さない。移行の都合で一時導入した互換レイヤも、役目を終えた時点で削除する。

---

## 本ドキュメントの債務 (= 何が書いてあるか)

本ファイルの責務は **「過去〜未来の作業計画 + incident postmortem の母艦」**。

- **書く**: Wave 1/2/3 計画 / 各 §4.X の詳細仕様 (incident、設計判断、教訓) / 長期 backlog / マイルストーン履歴
- **書かない (= 他 doc に委譲)**:
  - 「**今**」 の sprint 進捗 / 当日のゴール → [`TASKS.md`](TASKS.md) (current sprint dashboard、新セッションが最初に読む)
  - 「**OK か判定する基準**」 (V1-V6 検証ゲート) → [`../runbook/04_検証.md`](../runbook/04_検証.md) (検証 canonical 定義)
  - 「**やる手順**」 (`make deploy-all` の打ち方) → [`../runbook/05_運用.md`](../runbook/05_運用.md) (PDCA / runbook)

これは hedging label 禁止 (CLAUDE.md §「⛔ ゴール劣化禁止」) と表裏一体: 進捗を 3 箇所に書くと「片方だけ ✅ にして実は未達」のような虚偽が起きやすい → **進捗は TASKS.md に single source of truth** で集約する。

---

## 現在地 (2026-05-04 更新)

### destroy-all + state_recovery 徹底実装 — 完了 ✅

| # | 作業 | 状態 | 証跡 |
|---|---|---|---|
| 1 | `prevent_destroy` 撤回 + **state rm + terraform import pattern** への根本修正 | ✅ | §4.9 K fix。`infra/terraform/modules/vector_search/main.tf` から `lifecycle.prevent_destroy = true` 撤去、`scripts/setup/destroy_all.py` に `PERSISTENT_VVS_RESOURCES` + `state_rm` ループ、`scripts/setup/deploy_all.py` の tf-apply 前に `import_persistent_vvs_resources` 呼出し、`scripts/infra/vertex_import.py` 新規 |
| 2 | **destroy-all contract test 拡張** (旧 9 → **新 15 件**) | ✅ | `tests/integration/workflow/test_destroy_all_contract.py`。昨晩 hang した事象 (Composer/GKE/Cloud Run) を構造的 guard だけで捕まえられないため、incident postmortem を契約化:<br/>・`test_runbook_documents_emergency_kill_switch_for_composer_gke_cloudrun`<br/>・`test_runbook_documents_orphan_state_cleanup_after_emergency_delete`<br/>・`test_destroy_all_lessons_learned_documented_in_roadmap`<br/>・`test_deploy_all_invokes_state_recovery_before_tf_apply` (12 helper を pin)<br/>・`test_state_recovery_iam_sa_mapping_matches_terraform`<br/>・`test_runbook_warns_against_bare_state_rm_without_state_recovery` |
| 3 | **runbook §1.4-emergency 新節追加** | ✅ | `docs/runbook/05_運用.md` に緊急 kill switch (4 行コピペ可) + tfstate orphan cleanup 手順 + 状態確認 checklist + `make state-recover` 推奨 (bare `state rm` 警告) |
| 4 | **tfstate orphan cleanup** (緊急 cleanup の副作用 151 entries → 0) | ✅ | 2026-05-03 昼: stale `default.tflock` を `gcloud storage rm` で除去、150 entries を `state rm` ループで全削除、永続化 VVS 2 entries 含めて state count = **0** に到達 |
| 5 | **state_recovery.py 徹底実装** (12 GCP resource type、`alreadyExists` fail 回避) | ✅ | `scripts/infra/state_recovery.py` 新規 (660 行)。`alreadyExists` を 5 回 attempt の中で incremental に発見した resource type を全て吸収:<br/>・**IAM SA** 12 entries (composer 含む)<br/>・**BQ** dataset 3 + table 10<br/>・**Pub/Sub** topic 4 + subscription 3<br/>・**Cloud Function** 1 (pipeline-trigger)<br/>・**Eventarc** 2 trigger<br/>・**Cloud Run** 1 (meili-search)<br/>・**Artifact Registry** 1 (mlops)<br/>・**Secret Manager** 2 (meili-master-key, search-api-iap-oauth-client-secret)<br/>・**Dataform** 1 (hybrid-search-cloud)<br/>・**GCS bucket** 4 (models/artifacts/pipeline-root/meili-data)<br/>・**Vertex Feature Store** (Feature Group / Feature Online Store / Feature View)<br/>・**Vertex Feature Group Feature** 7 (rent/walk_min/age_years/area_m2/ctr/fav_rate/inquiry_rate)<br/>`deploy_all.py::_run_tf_apply` で tf-apply 直前に呼出し、idempotent (state にあれば skip / GCP に無ければ skip)。`make state-recover` も追加 |
| 6 | offline 検証 | ✅ | `make check` **649 passed, 1 skipped** / `make check-layers` PASS / `make tf-validate` Success / contract test 15/15 PASS |
| 7 | live verify (`deploy-all` / `run-all-core` / `check_retrain` / **V5 E2E**) | ✅ | Run 6 + **2026-05-03 Composer 再学習 E2E**（実装カタログ・[`TASKS.md`](TASKS.md)）。**destroy-all** は [`TASKS.md`](TASKS.md) どおり **最後（V3）** |

### 完了済み実装・検証の正本

- **[`docs/architecture/03_実装カタログ.md`](../architecture/03_実装カタログ.md)** — Wave 1/2、Composer V5、F1–F5、Run 履歴、検証サマリの **アーカイブ**（TASKS は載せない細目）
- [`docs/runbook/05_運用.md`](../runbook/05_運用.md) (§1.4-emergency + state-recover)
- [`tests/integration/workflow/test_destroy_all_contract.py`](../../tests/integration/workflow/test_destroy_all_contract.py) (15 件)
- [`scripts/infra/state_recovery.py`](../../scripts/infra/state_recovery.py)
- §4.9 / §4.10（本 roadmap）

### 残り作業（優先順位は [`TASKS.md`](TASKS.md) に集約）

1. **✅ 死守** — **V5 E2E** は **2026-05-03 Run** で実測クローズ（[`TASKS.md`](TASKS.md) checklist）。
2. **準死守（本線）** — **V4** 2 周目 `deploy-all`（`terraform import` / state_recovery 経路の live）
3. **余力** — **V6** parity / `live_gcp`（e2e acceptance gate）
4. **最後** — **V3** `destroy-all` live（破壊的）

補足: `deploy-all` Run 6、`run-all-core`、`check_retrain` live は達成済み（実装カタログ検証表）。長文の再掲はしない。

### 学び (本 session で固定化)

- terraform `lifecycle.prevent_destroy = true` は依存閉包内で touch される resource を block できない → **state 操作 (state rm + import) で表現するほうが安全** (§4.9 K fix で適用)
- 緊急 cleanup (`gcloud delete --async`) の副作用で tfstate orphan が大量に残る → **stale lock を `gcloud storage rm` で除去 → `state rm` ループ** が runbook 化済 (§1.4-emergency)
- incident postmortem は **contract test として固定化** しないと将来同じ誤った PR で再導入されるリスクあり → **6 件追加で固定化** (incident 3 + state_recovery 3)
- 全件 `state rm` 後の deploy-all は **GCP 残置 resource との `alreadyExists` 衝突** で fail する → state_recovery.py で **12 GCP resource type を type-by-type に import** することで idempotent 化。bare `state rm` だけで cleanup する runbook recipe は contract test で禁止

---

## 0. 前提と非負ルール (作業前に必ず確認)

- **中核 5 要素は不変**: Meilisearch BM25 / multilingual-e5 / ベクトルストア (Phase 4 = BQ `VECTOR_SEARCH` / Phase 5+ = Vertex AI Vector Search) / RRF / LightGBM LambdaRank
- **Phase 7 の canonical 挙動は 1 本にする**: `/search` の本線は Vertex Vector Search + Feature Online Store とし、BigQuery fallback や backend 切替スイッチを最終形に残さない
- **embedding 生成履歴・メタデータの正本は BigQuery 側**: Vertex Vector Search は本番 serving index、source は BQ embedding テーブル (`feature_mart.property_embeddings`)
- **Feature Store (Phase 5 必須)** を Phase 7 でも継承: training-serving skew 防止のため、Feature Online Store 経路を canonical とする
- **Meilisearch / Redis 同義語辞書は据え置き**: 実案件 reference architecture (Elasticsearch + Redis 同義語辞書) を教材向け substitute で維持しつつ、本 phase でも中核コードの意味を崩さない
- **Feature parity invariant 6 ファイル原則** は SemanticSearch / FeatureFetcher 変更でも継続 PASS
- **Cloud Composer は Phase 7 = canonical で本実装、Phase 6 が論理境界 (2026-05-03 改訂)**: 本 Phase 7 で `daily_feature_refresh` / `retrain_orchestration` / `monitoring_validation` の 3 本 DAG が orchestration 本線として本実装されており、PMLE step (Dataflow / BQML / SLO / Explainability) も同 DAG に増設済み。Vertex `PipelineJobSchedule` は完全撤去、Cloud Scheduler / Eventarc / Cloud Function trigger は本線から軽量代替へ格下げ。Phase 5 / 6 は論理 Phase であり、Phase 5 では Composer は理解上扱わず、Phase 4 軽量経路を本線として継続するという理解。Phase 6 は Composer 本線化の論理境界として位置づけ、Phase 7 配下の本実装を参照する。orchestration 二重化を作らない (詳細は親 [`README.md` §「Cloud Composer の位置づけ」](../../../../README.md))。Wave 2 GCP インフラの中で Composer 関連 (Composer 環境 Terraform + DAG deploy) も含む

---

## 1. 現状ギャップ

詳細な完了差分は [`docs/architecture/03_実装カタログ.md`](../architecture/03_実装カタログ.md) を正本とする。

残ギャップ（優先順は [`TASKS.md`](TASKS.md)）:
- **V4** — 2 周目 `deploy-all`（import 経路の live 再検証）
- **V6** — **既存 deploy 上** `RUN_LIVE_GCP_ACCEPTANCE=1 pytest tests/e2e/test_phase7_acceptance_gate.py -m live_gcp`（**full recreate** は `test_phase7_full_recreate_gate.py` に分離）
- **V3** — `destroy-all` live 1 周（最後）
- KFP 2.16 互換の運用上の回避は DAG / runner で継続（詳細は実装カタログ）
- [`docs/architecture/01_仕様と設計.md`](../architecture/01_仕様と設計.md) の最終同期

---

## 2. 移行戦略

### 2.1 暫定互換レイヤの扱い

Wave 1 ではローカル完結のために一時的な backend 切替と fallback を導入したが、**教育コードの完成条件はそれらを削除すること**。`BigQuerySemanticSearch` / `BigQueryFeatureFetcher` / backend 切替 env / legacy alias は Wave 2 の live 検証後に撤去し、Phase 7 の canonical 実装を 1 本に収束させる。

### 2.2 補足

- 実装方針や移行履歴の詳細は `03_実装カタログ.md` を正本とする

---

## 3. Wave 1 — 検索アプリ層 (本 roadmap の主タスク)

残（Wave 1 名称は歴史的経緯 — **offline parity** は `tests/integration/parity/`、**live V6** は e2e gate）:
- [ ] **V6** — `RUN_LIVE_GCP_ACCEPTANCE=1 pytest tests/e2e/test_phase7_acceptance_gate.py -m live_gcp`（既存環境）。optional: `RUN_LIVE_GCP_FULL_RECREATE=1` … `test_phase7_full_recreate_gate.py`
- [ ] Cloud Logging ベースの eventual consistency 観測
- [ ] KFP 2.16 import 互換 issue の根本対処

---

## 4. Wave 2 — GCP インフラ層 (Wave 1 完了後 = 着手可能、**クラウド側の主作業計画**)

> **Wave 1 のローカル完結が完了したので、Wave 2 は GCP リソース provision に集中できる。**
> Wave 1 の検証残課題 (live GCP smoke、KFP 2.16 互換 issue) もここで吸収する。
>
> **位置付け**: 本セクションは **クラウド側 (GCP インフラ) の修正作業計画の母艦**。親 [`README.md`](../../../../README.md) は教育設計、本 phase [`docs/01_仕様と設計.md`](../architecture/01_仕様と設計.md) は仕様 canonical、本セクションが **「いつ何を Terraform / kubectl / gcloud で叩くか」の作業計画** を持つ。

### 4.0 Wave 2 残タスク

- [x] Composer DAG import layout 修正 (`composer_deploy_dags.py` 反映済、646 PASS)
- [x] **destroy-all contract test 拡張** (旧 9 → 新 15 件、incident postmortem 3 + state_recovery 3 を契約化、本 session 2026-05-03)
- [x] **runbook §1.4-emergency 新節追加** (緊急 kill switch + orphan state cleanup + state-recover 推奨、本 session 2026-05-03)
- [x] **tfstate orphan cleanup** (151 entries → 0 達成、本 session 2026-05-03 昼)
- [x] **state_recovery.py 徹底実装** (12 GCP resource type、5 回 attempt の incremental 発見を吸収、本 session 2026-05-03 夕、§4.10 参照)
- [x] `make deploy-all` の **live 完走** (Run 6、`state_recovery` 12 type 版 — 実装カタログ)
- [x] `make run-all-core`（同一 sprint 実測 PASS）
- [x] **`retrain_orchestration` の死守 E2E** — [`TASKS.md`](TASKS.md) checklist（**2026-05-03 Run 実測クローズ**）。経緯・F1–F5・V5-8 は [`03_実装カタログ.md`](../architecture/03_実装カタログ.md) § Composer/V5
- [ ] **V4** — `make deploy-all` **2 周目**（import 経路・[`04_検証.md` §0 V4](../runbook/04_検証.md)）
- [ ] **V6** — opt-in e2e（[`test_phase7_acceptance_gate.py`](../../tests/e2e/test_phase7_acceptance_gate.py)）。full recreate: [`test_phase7_full_recreate_gate.py`](../../tests/e2e/test_phase7_full_recreate_gate.py)
- [ ] `make destroy-all` の **live 1 周 re-verify**（§4.9、[`TASKS.md`](TASKS.md) で **優先度「最後」**）

### 4.1 Composer DAG（W2-4 / V5）

**現状**: BashOperator 経路は撤去済み。**KubernetesPodOperator** + **composer-runner** + `_pod.py`（[`03_実装カタログ.md`](../architecture/03_実装カタログ.md) § Composer/V5）。`check_retrain` は live success（Run 4）。**クライアント説明に必要な完了条件**は §0 / [`TASKS.md`](TASKS.md) の **死守ライン**（全文 DAG + `/search` 健全性）まで。**「task SUCCEEDED は別 sprint」という記述は行わない**。

### 4.7 Cloud Composer 本実装 (W2-4、Phase 7 = canonical / Phase 6 は論理境界)

**Phase 7 で Composer module / 3 DAG / make target / scripts を本実装する** (= 教材コード完成版 / canonical 起点に必要な技術が Phase 7 に揃っている。Phase 6 は論理 Phase として本 Phase の本実装を参照する位置づけ)。

実装済み内容は [`docs/03_実装カタログ.md`](../architecture/03_実装カタログ.md) を正本とする。

コスト見積もりは [docs/05_運用.md](../runbook/05_運用.md) を正本とする。

### 4.8 Wave 1 由来の負債解消 (W2-9、並行可)

- [ ] KFP 2.16 互換 issue の根本対処
- [ ] `tests/integration/parity/*` の live 実行

### 4.9 VVS 永続化アーキテクチャ — MVP 完了（追加 hardening は §4.9 末 backlog）(W2-10)

**背景**: Vertex Vector Search の課金構造は非対称。Index 自体と空の Index Endpoint は **無料** (公式: "Models that are not deployed or have failed to deploy are not charged.")、課金されるのは `deployed_index` (replica 起動状態) のみ。Index build に 5-15 min、Endpoint 作成 + DNS propagation に数分かかるため、PDCA cycle ごとに作り直すと deploy-all 全体の短縮効果が消える。

#### 設計の試行錯誤 (2026-05-03 destroy-all 失敗事故)

**初版 (失敗) — `lifecycle.prevent_destroy = true`**:
1. Terraform module の Index / Endpoint に `prevent_destroy = true` を設定
2. `destroy_all.py` で state_list 全件から persistent を除外して `-target` 指定で destroy
3. 期待: persistent な 2 addr (Index / Endpoint) は terraform が destroy しないので残る

**実際に起きたこと**:
- destroy-all を 2 回連続実行、両方とも `Error: Instance cannot be destroyed` で `[6/6]` 本体 destroy 中断
- state は 180 / 178 addr 残置、**Composer (RUNNING) + GKE (RUNNING) + Cloud Run + Feature Online Store** が課金継続
- 緊急対処として `gcloud composer environments delete --async` / `gcloud container clusters delete --async` / `gcloud run services delete` で直接削除

**真因**: Terraform の `lifecycle.prevent_destroy = true` は **依存閉包で touch される resource を block できない**。`-target` filter で除外しても、依存関係解決時に Index / Endpoint が引っ張られ、prevent_destroy 違反で全 destroy が止まる。`prevent_destroy` は「この resource を直接 destroy 対象にした場合に止める」までで、依存連鎖を止める仕組みではない。

#### 根本修正 (実装済 ✅、2026-05-03 = K fix)

`prevent_destroy` を撤回し、**state rm + GCP 残置 + 次回 deploy-all で `terraform import` で復元** する pattern に転換:

- [`infra/terraform/modules/vector_search/main.tf`](../../infra/terraform/modules/vector_search/main.tf): Index / Endpoint から `lifecycle.prevent_destroy = true` を削除 (再導入は contract test で block)
- [`scripts/infra/vertex_import.py`](../../scripts/infra/vertex_import.py) **(新規)**: `gcloud ai indexes/index-endpoints list` で existing GCP resource の `name` を取得し、`terraform import <addr> <gcp_resource_name>` で state へ取り込む。state に既に entry があれば skip、GCP に無ければ skip (= 初回 deploy 扱い)
- [`scripts/setup/destroy_all.py`](../../scripts/setup/destroy_all.py): step `[2/6++]` で `module.vector_search` の Index / Endpoint / deployed_index を `terraform state rm` で外す (GCP 上は残置、Index/Endpoint は無料、deployed_index は `[2/6+]` で gcloud undeploy 済)。step `[6/6]` 本体 destroy では state にもう存在しないので touch されない
- [`scripts/setup/deploy_all.py::_run_tf_apply`](../../scripts/setup/deploy_all.py): tf-apply の前に `import_persistent_vvs_resources` を呼んで existing GCP resource を state に import。これにより `terraform plan` は「Index/Endpoint = no-op、deployed_index のみ create」となり deploy-all が短縮される
- [`tests/integration/workflow/test_destroy_all_contract.py::test_destroy_all_persists_vvs_index_and_endpoint`](../../tests/integration/workflow/test_destroy_all_contract.py): contract を更新 — (1) lifecycle block 内に `prevent_destroy = true` が **無い** (2) destroy_all が `state_rm` で永続化を実施 (3) deploy_all が `import_persistent_vvs_resources` を呼ぶ
- [`docs/runbook/05_運用.md §1.4`](../runbook/05_運用.md): 「残るもの」に Index / Endpoint を追加、deploy-all 短縮効果 (27 min → 10-15 min) を明記

検証: **649 PASS** (本 session 朝 contract test 3 件追加で 12 件、646 → 649)、`terraform validate` Success

期待効果:

| シナリオ | 従来 | 新 |
|---|---|---|
| 初回 deploy-all | 27-30 min | 27-30 min (Index build 込み) |
| 2 回目以降 deploy-all | 27-30 min | **10-15 min** (deployed_index attach のみ) |
| 維持コスト (放置時) | replica 課金 ¥1,460/日 | **¥0/月** (Index/Endpoint は無料) |

#### 残タスク

**今 sprint の最終 verify**:
- [x] **incident postmortem の contract 固定化** (本 session 朝): 旧 9 → 新 15 contract test (incident 3 + state_recovery 3)、runbook §1.4-emergency 追加、`make check` 649 PASS
- [x] **tfstate orphan cleanup** (151 entries → 0 達成、本 session 2026-05-03 昼)
- [x] **state_recovery.py 徹底実装** (12 type、§4.10、本 session 夕)
- [ ] **新 destroy-all (state rm + import pattern) の live 1 周検証**: 進行中 — `make deploy-all` → 動作確認 → `make destroy-all` を 1 周し、(a) `[2/6++] state rm 永続化 VVS` ログが出る (b) `[6/6]` 本体 destroy が complete で終わる (c) GCP 上に Index / Endpoint だけ残る (d) 次回 deploy-all step 6 で `terraform import` ログが出て deployed_index のみ create される、を確認

**今 sprint で得られた教訓 (lesson learned)**:
- `terraform lifecycle.prevent_destroy = true` は依存閉包内で touch される resource は block できない。**state 操作 (state rm / state import) で表現するほうが安全**
- destroy-all は冪等であるべきだが、全 step PASS を通せていない場合の手動 cleanup 経路 (`gcloud composer environments delete --async` 等) を runbook に明示する必要あり → **本 session 朝で [docs/05_運用.md §1.4-emergency](../runbook/05_運用.md) に追加済 ✅** (緊急 kill switch + tfstate orphan cleanup 手順 + 状態確認 checklist)
- 緊急時 `gcloud composer environments delete --async` + `gcloud container clusters delete --async` + `gcloud run services delete` の 3 つで主要課金は数分で止まる事を確認 → **runbook §1.4-emergency に固定化済 ✅**
- incident postmortem は **contract test として固定化** しないと将来同じ誤った PR で再導入されるリスクあり → **本 session 朝で [test_destroy_all_contract.py](../../tests/integration/workflow/test_destroy_all_contract.py) に 3 件追加済 ✅** (旧 9 → 新 12 件): runbook 緊急節 / orphan cleanup 手順 / §4.9 lesson learned の存在を pin
- destroy-all 失敗時の **state inconsistency 検出** が未実装: `state list | wc -l` が想定より多ければ alert する health check を `make destroy-status` として追加する案 → **backlog**（下記、優先度は V5 E2E・V4 の後）

**Backlog（優先度较低・Wave 2/3 跨ぎ）**:
- [ ] **Stack 分離 (PR 1-3 相当)**: `infra/terraform/stacks/{persistent,vector_search,core}/` に分離し、`terraform_remote_state` で接続。core stack の destroy で deployed_index のみ消える設計が構造化され、誤って Index / Endpoint を destroy 対象にしてしまう事故を block (state rm pattern より strong な保護)
- [ ] **Cloud Scheduler 自動 undeploy (PR 4 相当)**: deployed_index 残置による課金事故防止。4h timeout で強制 undeploy する Cloud Scheduler job
- [ ] **Billing Budget Alert (PR 5 相当)**: 日次 ¥3,000 閾値で notification、加えて監視ダッシュボード
- [ ] **destroy-all health check Make target (新規候補)**: `make destroy-status` で state 残数 + GCP 主要 resource (Composer / GKE / Cloud Run / FOS) の生存をチェック → 異常があれば exit 1。寝る前確認に使える
- [ ] **緊急 kill switch Make target (新規候補)**: `make destroy-emergency` で `gcloud composer environments delete --async` + `gcloud container clusters delete --async` + `gcloud run services delete` を一気に投げる (state は後で cleanup)

破綻条件 (注意):
- Embedding model のバージョン変更 (次元 / 分布変更) → Index 再 build 必要 (27 min の出戻り)
- Vector Search の major upgrade → 構造変更で移行作業発生
- 数ヶ月放置時の Google 側 GC (公式に未明記、念の為 monthly health check 推奨)
- **deployed_index 残置が最大リスク** (1 replica = ¥1,460/日 = ¥44,000/月) → Cloud Scheduler 自動 undeploy が後続 sprint で必須
- **state import 失敗時のリスク**: `vertex_import.py` の gcloud list が空 → terraform plan は「新規 create」と判定 → existing GCP resource と name 衝突で 409。再現条件: destroy-all 後に GCP 側で手動 delete された場合 / 別 region で list した場合。回避策: `vertex_import.py` 内の region 引数を必ず env から取る (実装済)

### 4.10 state_recovery 徹底実装 (W2-11、本 session 2026-05-03 夕)

**背景**: §4.9 K fix で VVS 永続化を `state rm + import` pattern に移行したが、同じ pattern を **VVS 以外の全 GCP resource type** に拡張する必要があった。きっかけは tfstate orphan cleanup (151 entries → 0) 後の `make deploy-all` Run 1-5 で、`alreadyExists` errors が **type-by-type に incremental 発見** されたこと:

| Run | 失敗 type | 追加した recovery |
|---|---|---|
| 1 | `sa-composer` IAM SA | `_recover_iam_sas` (12 SA: api/job_train/job_embed/dataform/scheduler/pipeline/endpoint_encoder/endpoint_reranker/pipeline_trigger/external_secrets/github_deployer/composer) |
| 2 | Artifact Registry `mlops` / Secret Manager `meili-master-key` `search-api-iap-oauth-client-secret` / Dataform `hybrid-search-cloud` | `_recover_artifact_registry` / `_recover_secret_manager` / `_recover_dataform` |
| 3-4 | GCS `mlops-dev-a-{models,artifacts,pipeline-root,meili-data}` | `_recover_gcs_buckets` |
| 5 | Vertex Feature Group `property_features` / Feature Online Store `mlops_dev_feature_store` / Feature View `property_features` | `_recover_feature_store` (Feature Group + Feature Online Store + Feature View) |
| 6 | Vertex Feature Group Features 7 個 (rent/walk_min/age_years/area_m2/ctr/fav_rate/inquiry_rate) | `FEATURE_GROUP_FEATURES` 追加 + `_recover_feature_store` 内ループ拡張 |

**実装** (実装済 ✅):

- [`scripts/infra/state_recovery.py`](../../scripts/infra/state_recovery.py) **新規 (~700 行)**: 12 type の generic recovery framework。各 type ごとに「GCP list → state list 突合 → terraform import」の idempotent ループ。`_aiplatform_get` は v1beta1 REST 経由 (gcloud list 未対応の Feature Store / Feature Group Feature 用)
- [`scripts/setup/deploy_all.py::_run_tf_apply`](../../scripts/setup/deploy_all.py): tf-apply の前に `recover_orphan_gcp_resources(...)` を呼出し (`vertex_import.py` の VVS recovery と並列)
- [`Makefile`](../../Makefile): `make state-recover` target 追加 (`uv run python -m scripts.infra.state_recovery`)
- [`tests/integration/workflow/test_destroy_all_contract.py`](../../tests/integration/workflow/test_destroy_all_contract.py): 3 件追加 (旧 12 → 新 15)
  - `test_deploy_all_invokes_state_recovery_before_tf_apply`: 12 helper (`_recover_iam_sas` / `_recover_bq` / `_recover_pubsub` / `_recover_cloudfunctions` / `_recover_eventarc` / `_recover_cloud_run` / `_recover_artifact_registry` / `_recover_secret_manager` / `_recover_dataform` / `_recover_gcs_buckets` / `_recover_feature_store` / FEATURE_GROUP_FEATURES) を pin
  - `test_state_recovery_iam_sa_mapping_matches_terraform`: `IAM_SA_NAMES` と `infra/terraform/modules/iam/main.tf` の `google_service_account` 宣言を一致確認
  - `test_runbook_warns_against_bare_state_rm_without_state_recovery`: runbook §1.4-emergency が `make state-recover` を bare `state rm` の前に推奨することを pin

**冪等性の保証**:
- `_state_has(addr)`: state に既に entry があれば skip
- GCP 側に存在しない resource は skip (= 初回 deploy 扱い)
- 何度叩いても余分な import は走らない (`make state-recover` は smoke として複数回叩いても安全)

**適用条件**:
- 教材 dev project (`mlops-dev-a`) 専用。別 project 流用時は GCS bucket 名 / Feature Store ID を mapping 拡張要
- IAM bindings (`google_project_iam_member` 等) は recover しない (依存 SA を import すれば tf-apply で create_or_read される)

**残タスク**:
- [x] **Run 6 live 完走** (12 type recovery 完備版で `make deploy-all` が `Apply complete` まで到達 — §7 M-GCP と整合)
- [ ] state_recovery が新規 GCP resource 追加時に自動拡張されない件は技術負債として記録 (新 resource 追加時に手動で mapping 追加要、契約 test で漏れ検出)

---

## 5. Wave 3 — docs / reference architecture との整合 (確認のみ)

- [ ] 本 phase [docs/01_仕様と設計.md](../architecture/01_仕様と設計.md) §「実案件想定の reference architecture」(Phase 5 docs を参照する旨) が最新であること — W2-8 削除と同期して再確認 (canonical 1 経路化後)
- [ ] コードに `Elasticsearch` / `synonym` / `query expansion` 等の固有名が混入していないことを `scripts/ci/layers.py` の禁止語リスト (or grep based check) で守る — 任意の追加チェック (現状コード grep では hit 無しを 2026-05-02 終端で確認)
- [x] [docs/05_運用.md](../runbook/05_運用.md) の「semantic 経路」「feature 取得経路」記述は更新済

---

## 6. リスクと回避

| 状態 | リスク | 回避 |
|---|---|---|
| ✅ 対処済 | Composer DAG upload layout / V5 runner | [`03_実装カタログ.md`](../architecture/03_実装カタログ.md) § Composer/V5。死守は [`TASKS.md`](TASKS.md) E2E |
| ⚠ 残存 | KFP 2.16 互換 issue | `scripts.ops.train_now` で暫定回避、根本 fix は別 PR |
| ⏳ Wave 2 | Feature Online Store のコスト | `make destroy-all` 運用を維持 |

---

## 7. マイルストーン

| ID | フェーズ | 状態 | メモ |
|---|---|---|---|
| M-Local | ローカル | ✅ | 詳細は `03_実装カタログ.md` を参照。`make check` 649 PASS |
| M-Contract | destroy-all 契約 | ✅ | 旧 9 → 新 12 件 (incident postmortem を契約化、本 session 朝 2026-05-03)。runbook §1.4-emergency 緊急 kill switch + tfstate orphan cleanup 手順を追加 |
| M-GCP | GCP | 🟡 | **死守（V5 E2E）✅** 2026-05-03 Run。**本線残**: **V4** 2 周目 deploy-all → **V6** e2e `live_gcp` → **V3** `destroy-all`（[TASKS.md](TASKS.md)）。**済**: tfstate orphan **151→0**、deploy-all Run 6、run-all-core、Composer 再学習 E2E 完走。詳細は [03_実装カタログ.md](../architecture/03_実装カタログ.md) 検証表 |
| M-Docs | docs | ⏳ | `01_仕様と設計.md` の最終同期が残り |

---

## 8. 関連 docs

- 親リポ:
  - [README.md](../../../../README.md) §1 教材対象外 / §3 非負制約 / §4 学習運用
  - [CLAUDE.md](../../../CLAUDE.md) §「非負制約 (Phase 3/4/5/6/7 共通)」
  - [docs/01_仕様と設計.md](../../../../docs/architecture/01_仕様と設計.md) §「ハイブリッド検索の仕様と設計 (Phase 3-7 共通)」
- 本 phase:
  - [README.md](../README.md)
  - [CLAUDE.md](../CLAUDE.md)
  - [docs/01_仕様と設計.md](../architecture/01_仕様と設計.md) §「実案件想定の reference architecture」(Phase 5 を継承)
  - [docs/TASKS_ROADMAP.md](TASKS_ROADMAP.md) Port / Adapter / DI 大枠
  - [docs/decisions/](../decisions/README.md) 過去の制約決定 (ADR 0001〜0008)
- Phase 5 (継承元):
  - [5/study-hybrid-search-vertex/docs/01_仕様と設計.md](../../../../5/study-hybrid-search-vertex/docs/01_仕様と設計.md)
  - [5/study-hybrid-search-vertex/docs/02_移行ロードマップ.md](../../../../5/study-hybrid-search-vertex/docs/02_移行ロードマップ.md)
