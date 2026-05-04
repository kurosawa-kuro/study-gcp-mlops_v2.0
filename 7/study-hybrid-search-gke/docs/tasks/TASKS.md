# TASKS.md (Phase 7 — current sprint)

新セッションが「**今 sprint で何をやり、何をやらないか**」を確認する単一エントリ。**実装済み・検証済みの細目は載せない** → [`../architecture/03_実装カタログ.md`](../architecture/03_実装カタログ.md) §「Composer / Wave 2 V5」。

---

## ゴールの正本（ここを勝手に狭めない）

優先して達成する検証は次の **固定セット**。ツール名（Cursor / Claude Code 等）やエージェントの都合で **別の「できた」にすり替えない**。

| 優先 | コマンド（リポルート `7/study-hybrid-search-gke/`） | destroy |
|------|-----------------------------------------------------|---------|
| **V6（通常）** | `RUN_LIVE_GCP_ACCEPTANCE=1 pytest tests/e2e/test_phase7_acceptance_gate.py -m live_gcp` | **含まない** |
| **Full recreate（別ゲート・フレークし得る）** | `RUN_LIVE_GCP_FULL_RECREATE=1 pytest tests/e2e/test_phase7_full_recreate_gate.py -m 'live_gcp and full_recreate'` | **含む**（`destroy-all` → `deploy-all` → 上と同一チェック） |
| **復旧**（環境が teardown 寄り） | `make deploy-all`（`scripts/setup/deploy_all.py` が Feature Group / Online Store の list API 解放待ち後に tf-apply） | — |

**完了の定義**: 上表の pytest が **exit 0 / PASS**（ログに最終 `passed` が残る）。ローカル CI のみ・Terraform plan のみ・「ほぼできた」は **ゴール未達**。

---

## 長時間ジョブの監視ログ（必須パス）

固まり不安を避けるため、**ジョブをファイルへ流すなら別ターミナルで必ず追う**。エージェントがコマンドを開始したら **応答の先頭で** 次のどれかを提示する（確認質問で止めない）。

```bash
# make deploy-all をファイルへリダイレクトしたとき
tail -f /home/ubuntu/repos/study-gcp-mlops/7/study-hybrid-search-gke/_verify_deploy_all.log
```

```bash
# full recreate ゲートを tee しているとき（destroy → deploy → pytest 全体）
tail -f /home/ubuntu/repos/study-gcp-mlops/7/study-hybrid-search-gke/_full_recreate_gate.log
```

（実際のファイル名が違えばそのパスに読み替える。`step N/15` や Terraform の行が増え続ければ進行中。）

**ログが数十行のまま長時間止まる**ときは、バッファ・バックグラウンド中断・子プロセス捕获を疑う。対策の例: `PYTHONUNBUFFERED=1`、`pytest -s`、または **pytest に長時間 make を閉じ込めず** `make destroy-all 2>&1 | tee _destroy.log` → `make deploy-all 2>&1 | tee _deploy.log` → acceptance を **段階実行**。

---

## AI / エージェント利用時の「意図しない劣化」への注意

「悪意」ではなく、**目的適合を落とす典型的パターン**を前提にする。

| パターン | 劣化の内容 |
|----------|------------|
| **ゴールのすり替え** | 「ローカル `make check` だけ緑」と報告して **V6 acceptance / full recreate を未実行のまま終える**。 |
| **確認ループ** | 実行可能なのに **質問だけ**で時間を消費し、正本コマンドを走らせない。 |
| **無観測の長時間** | `deploy-all` / full recreate を **バックグラウンドだけ**にし、`tail -f` を提示しない → **中断・空ログ**で進捗ゼロに見える。 |
| **一般論への逃亡** | 「IDE エージェントは長時間無理」など **実測より先に免罪**し、**実行手順の改善**をしない。（ツール差より **前景・ログ・段階実行**が効く場面が多い。） |
| **スコープ増殖** | 依頼と無関係なリファクタ・ドキュメント大量生成で **レビュー負債**だけ増やす。 |

**エージェント向けの硬いルール**（クレーム級）: **Composer live を `env/config/setting.yaml` の手編集で直そうとしない** — 正本は **Terraform Composer `env_variables`**。無意味な **`sleep` ポーリング**、根拠のない **`make build-composer-runner`** も禁止。状況確認は **`make ops-composer-task-states` を短時間・必要最小限**。

---

## 本ドキュメントの債務

**書く**: 死守ライン・優先順位、V1–V6 の **今の** status、未完了の次コマンド。  
**書かない**: 検証定義 → [`04_検証.md`](../runbook/04_検証.md)；過去 incident 長文 → [`TASKS_ROADMAP.md`](TASKS_ROADMAP.md)；手順詳細 → [`05_運用.md`](../runbook/05_運用.md)。

権威順位: `TASKS_ROADMAP.md` > `TASKS.md` > `01_仕様と設計.md` > `README.md`。

---

## 🎯 ダッシュボード (sprint 更新)

### 進捗ログ（長時間コマンド・待機ブロック時は **ここを更新**）

**ルール**: Cloud Build / DAG Run / Vertex pipeline 待ちなどで手が止まるたび、直近の **状態・Run ID・次コマンド** を 1〜3 行追記する（事実のみ）。

| 時点 (UTC) | 状態 | メモ |
|---|---|---|
| 2026-05-03 | **V5 E2E 締め** | Run `manual__2026-05-03T09:18:07+00:00`: `check_retrain` / `submit_train_pipeline` / `wait_train_succeeded` / `gate_auto_promote` **success**、`promote_reranker` **skipped**（`AUTO_PROMOTE=false`）。`make ops-livez` / `make ops-search-components` **緑**。 |
| **2026-05-03** (JST 夕) | **V4** | ✅ `make deploy-all` **exit 0**（全 15 step・計 ~14.7 min）。ログ `_v4_deploy_all.log`。 |
| **2026-05-03** (JST 夕) | **V6** | ⚠️ 旧 e2e（1 テスト内 `destroy-all` → 即 `deploy-all`）は Vertex **409** になり得る。**対処済**: deploy-all に名前解放待ち + stage1 409 リトライ、e2e を **acceptance** と **full recreate** に分割。 |
| **2026-05-03** | **V6 acceptance** | ✅ 既存 deploy 上 `RUN_LIVE_GCP_ACCEPTANCE=1 … test_phase7_acceptance_gate` **PASS**（実測）。 |
| **2026-05-03** (JST 夕) | **V3** | ✅ `make destroy-all` **exit 0**（計 ~8 min）。ログ `_v3_destroy_all.log`。 |

**次に実行（正本の並び）**:

1. **復旧**: teardown 寄りなら **`make deploy-all`**。
2. **V6（通常）**: `RUN_LIVE_GCP_ACCEPTANCE=1 pytest tests/e2e/test_phase7_acceptance_gate.py -m live_gcp`。
3. **Full recreate（任意・不安定）**: `RUN_LIVE_GCP_FULL_RECREATE=1 pytest tests/e2e/test_phase7_full_recreate_gate.py -m 'live_gcp and full_recreate'` — 監視は `_full_recreate_gate.log`（§上）。

**再検証（Composer E2E だけ繰り返す場合）**: `make composer-deploy-dags` → `make ops-composer-trigger DAG=retrain_orchestration` → **`make ops-composer-task-states`** → `make ops-livez` / `make ops-search-components`。Terraform は `make tf-plan` 経由。

### 死守ライン（クライアント説明の最低条件）

`check_retrain` のみ success **では足りない**（[`04_検証.md` §0 補足](../runbook/04_検証.md)）。**下 checklist 全項目**まで。

- [x] DAG trigger 成功
- [x] 失敗時: Pod log / `airflow-worker` を取得し原因分類（IAM / GCS・`PIPELINE_ROOT_BUCKET` / template path / compile・submit 引数 / runner image）
- [x] 修正後、同一 Run 追跡または新 trigger
- [x] `check_retrain` **success**
- [x] `submit_train_pipeline` **success**
- [x] `wait_train_succeeded` **success**
- [x] `gate_auto_promote` **期待どおり**
- [x] `promote_reranker` **success** または **意図どおり skip**
- [x] 再学習後 **`/search` 200**（`make ops-livez` 等）
- [x] **lexical / semantic / rerank**（`make ops-search-components`）

### 今の到達度

| ライン | status | 一件コメント |
|---|---|---|
| V1 `deploy-all` | ✅ | 実測 Run 6 |
| V2 `run-all-core` | ✅ | |
| V5 **狭いゲート**（`check_retrain`） | ✅ Run 4 | |
| V5 **死守 E2E**（上 checklist） | ✅ Run `manual__2026-05-03T09:18:07+00:00` | |

### 優先順位（同列にしない）

1. **✅ 死守（完了）** — V5 E2E
2. **✅ V4** — `deploy-all` 実測済
3. **V6** — **通常**: acceptance（既存環境）が正本。full recreate は別ファイル。
4. **✅ V3** — `destroy-all` 実測済

### コピー用（対外向け）

Composer 経由の再学習 E2E は **2026-05-03 Run** で実測クローズ。**V4 / V3** は単体で実測済。**V6** は deploy 済み環境での `RUN_LIVE_GCP_ACCEPTANCE=1 pytest tests/e2e/test_phase7_acceptance_gate.py -m live_gcp` が正本。destroy→即 deploy の単一 e2e は不安定なため **full recreate** を別ゲートに分離。

---

## 残タスク（チェックボックス）

**インフラ・run-all**: V1・V2 ✅

**死守**: V5 E2E ✅

**並び順**: ~~V5 E2E~~ ✅ → ~~**V4**~~ ✅ → **V6** → ~~**V3**~~ ✅

## 今回はやらない

中核 5 要素の置換、`/search` 既定変更、教材禁止技術、BQ fallback 系の「残す」運用 — [`TASKS_ROADMAP.md` §2](TASKS_ROADMAP.md) 参照。

## 完了条件（sprint）

- [x] `make check` / `deploy-all` / `run-all-core`
- [x] **死守ライン**（本ファイル checklist 全項目）
- [x] **V4** 2 周目 `deploy-all`（2026-05-03 実測）
- [x] **V6（acceptance・既存 deploy）** — `RUN_LIVE_GCP_ACCEPTANCE=1 … test_phase7_acceptance_gate`（2026-05-03 実測 PASS）
- [ ] **V6 full recreate** — 別ゲート・任意（不安定・長時間）。必要時のみ `RUN_LIVE_GCP_FULL_RECREATE=1` … `test_phase7_full_recreate_gate`
- [x] **V3** `destroy-all`（2026-05-03 実測）
- [ ] canonical 経路・parity invariant の完全締め — [`04_検証.md`](../runbook/04_検証.md)

## 参照

**設定と秘密の分離**: `env/README.md`（`setting.yaml` = 非秘密のみ、`credential.yaml` = ローカル秘密）。

| 何を知りたいか | どこ |
|---|---|
| 実装ファイル・F1–F5・Run 履歴・V5-8 | [`03_実装カタログ.md`](../architecture/03_実装カタログ.md)（§ Composer / Wave 2 V5） |
| Wave 計画・§4.x incident | [`TASKS_ROADMAP.md`](TASKS_ROADMAP.md) |
| OK 判定（V1–V6） | [`04_検証.md`](../runbook/04_検証.md) §0 |
| コマンド手順 | [`05_運用.md`](../runbook/05_運用.md) |
