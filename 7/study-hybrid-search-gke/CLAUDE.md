# CLAUDE.md

Phase 7 (`7/study-hybrid-search-gke`) で作業する Claude Code 向けガイド。**到達ゴール = 教材コード完成版の canonical 起点**。引き算で Phase 6 / 5 を派生させる戦略 (親 README §4) のため、本 phase に **PMLE 4 技術 + Cloud Composer 本線 orchestration + Phase 5 必須の Feature Store / Vertex Vector Search を本実装** し、Serving 層は Vertex AI Endpoint → GKE + KServe InferenceService。中核 (不動産ハイブリッド検索) は不変、推論を cluster-local HTTP に委譲。Phase 7 固有: KServe → Feature Online Store を **Feature View 経由で** opt-in 参照、TreeSHAP 用 explain 専用 Pod を独立 deploy。

詳細仕様は [`docs/architecture/01_仕様と設計.md`](docs/architecture/01_仕様と設計.md) (§3 で Composer canonical) と [`docs/tasks/TASKS_ROADMAP.md`](docs/tasks/TASKS_ROADMAP.md)。本 CLAUDE.md はそれらに従属。

---

## ⛔ ゴール劣化禁止 (= クライアント罰金回避ライン)

**最重要ルール**。本 phase の canonical 仕様 (= 「**本線**」「**必須**」「**canonical**」と書かれた要件) を未達のまま「完了」「OK」「W2-X 完了とみなす」と扱うのは禁止。違反するとクライアント契約見送り罰金レベル。

**禁止する hedging label の例**:
- 「深追いは別 sprint (候補)」
- 「現状で W2-X 完了とみなし、次のステージへ進む」
- 「Stage X.Y 未解決のまま完了扱い」
- 「task SUCCEEDED は別 sprint」「live verify は別 session」← canonical 必須項目に対しては禁止
- 「明日以降」「後追い」← canonical 必須項目に対しては禁止
- 判断 A/B が並列に書かれている場合、勝手に A を選んで B を「別 sprint」へ送る

**正しい扱い方**:
1. canonical 未達 = ⚠️ マーカー付きで「**canonical 未達 (= ゴール劣化)、追加 sprint 必須**」と明示
2. canonical 必須項目と機能影響低の項目を **明確に区別**してダッシュボード/roadmap に書く
3. 判断 A/B が並列に書かれた roadmap で、canonical 違反が生じる選択肢は ~~取り消し線~~ で不採用宣言する。User に明示確認せず勝手に採用しない
4. 「W2-X 完了とみなす」「Stage X.Y 完了扱い」を書く前に、本 CLAUDE.md と `docs/architecture/01_仕様と設計.md` の **canonical 要件と必ず照合**してから書く

**過去の incident** (2026-05-03): Phase 7 で Composer DAG `retrain_orchestration::check_retrain` が SUCCEEDED 未達なのに、過去 session の Claude が `TASKS_ROADMAP.md §4.1` で「A: 現状で W2-4 完了とみなす / B: SUCCEEDED まで深追い」のうち **A を勝手に採用** し、ダッシュボード V5 を「別 sprint 候補」扱いしていた。CLAUDE.md (本ファイル §「非負制約」と親 CLAUDE.md §「Cloud Composer」) は「**本線 retrain schedule は Composer DAG**」と明記しているため、SUCCEEDED 未達 = canonical の根幹未実証。User からの指摘:「やはり人工知能が悪さしてゴールを劣化させてた、クライアントから罰金レベル」。本 incident を踏まえ、`TASKS_ROADMAP.md §4.1` は B 採用 + A 取り消し線で書き直し済。

### ⏱ エージェントの時間コスト禁止（悪意と同等の扱い）

**クレーム・返金レベル**で禁止する。ユーザの残り時間と信頼を奪う行為として扱う。

1. **無意味に長いポーリングで session を占有しない** — 数十分の `sleep` ループで DAG / Vertex の完走を待ち続けない。短い **必要最小限の確認**は可。長時間処理は GCP 側／ユーザー手元に任せ、`make ops-composer-task-states` 等でスナップショットを返すに留める。
2. **不要な `make build-composer-runner` 禁止** — Dockerfile・runner 関連コードの実変更や stale 画像の証拠がないのに Cloud Build を回さない。
3. **根拠のない再試行禁止** — 失敗時はログ分類 → 必要なら 1 修正 → 1 検証。
4. **`env/config/setting.yaml` を死守・Composer live の修正手段にしない** — 正本は **`infra/terraform/modules/composer` の `env_variables`**（および Composer 注入の **GCP_PROJECT**）。また **setting は非クレデンシャル専用**（設計）。秘密は **`env/secret/credential.yaml`** / Secret Manager — setting に鍵を書く前提で提案しない。

---

## User 事前承認 (PDCA 学習用 dev project の自動化方針)

**対象 project**: `mlops-dev-a` (学習用 dev、`destroy-all` でゼロに戻すこと前提)。

User からの**包括的事前承認**として、本 phase の検証目的では以下の operation を **per-call の確認を取らずに直接実行してよい**。「最速で作成成功させて検証を完了する」ことが目的だから:

- `terraform apply -auto-approve` (stage 分割含む `-target` 付き)
- `terraform destroy -auto-approve` / `make destroy-all`
- `make deploy-all` / `make deploy-api` / `make deploy-kserve-models`
- `gcloud run deploy` / `gcloud ai endpoints undeploy-model + delete`
- `kubectl set image` / `kubectl rollout restart`
- BQ table の `deletion_protection` flip (destroy-all step 4 で実施)

**範囲制限**:
- 対象は本 phase (`mlops-dev-a` project) の Terraform 管理リソースのみ
- `git push --force` / 共有 main branch への push は引き続き user 確認が必要
- 別 project / 別 phase に波及するコマンドは事前承認外

**理由**: 本 project は **PDCA dev project (CLAUDE.md §1.0 設計意図)**。`destroy-all` で全消し → `deploy-all` で再構築 が前提のループ。確認プロンプトを挟むと PDCA が成立しない。

---

## 最初に読むもの (用途と読むタイミング)

ファイル名は番号 + 日本語 (Phase 横断で同番号比較できる学習設計のため不変) だが、各 docs の用途・読むタイミングは下表で明示する。**新セッションは `docs/tasks/TASKS.md` から始めること**。

| パス | 役割 | いつ読むか |
|---|---|---|
| [`docs/tasks/TASKS.md`](docs/tasks/TASKS.md) | 死守ライン・短いダッシュボード（検証済みの細目は `03_実装カタログ`） | **新セッション最初** |
| [`docs/tasks/TASKS_ROADMAP.md`](docs/tasks/TASKS_ROADMAP.md) | 決定的仕様 + 権威 1 位 + Wave / §4.x incident | スコープ・優先度・過去判断が必要な時 |
| [`docs/architecture/01_仕様と設計.md`](docs/architecture/01_仕様と設計.md) | 仕様 + アーキテクチャ canonical (§2 ハイブリッド検索 / §3 Composer 位置づけは Phase 横断 canonical) | 設計判断の根拠を確認する時。「なぜこう設計?」 |
| [`docs/architecture/03_実装カタログ.md`](docs/architecture/03_実装カタログ.md) | 実装物スナップショット (dir / file / DB / API / GCP リソースの 1:1 対応) | 「○○の実装はどこ?」「この機能のファイル群は?」 |
| [`docs/runbook/04_検証.md`](docs/runbook/04_検証.md) | 検証ゲート定義 + 「OK」判定基準 + 検証シナリオ (ローカル / GCP ゲート) | 検証実施時 / 「これで通ったと言えるか?」の判定時 |
| [`docs/runbook/05_運用.md`](docs/runbook/05_運用.md) | PDCA loop (`make deploy-all` / `destroy-all`) + 定常運用 + インシデント対応 | デプロイ・運用・PDCA 周回時 |
| [`docs/decisions/`](docs/decisions/) (ADR 0001〜0008) | 過去の制約決定の経緯 | 「なぜこうなった?」の経緯確認時 |
| `infra/manifests/` | search-api / KServe / policies / kustomization | k8s manifest を直接編集する時 |

---

## hybrid-search-gke の設計テーゼ

- **題材**: 不動産検索 (自由文クエリ + フィルタ → 上位 20 件)。3 段 = Meilisearch BM25 + Vertex Vector Search (ME5/ANN) → RRF → LightGBM LambdaRank
- **本実装 (canonical)**: Phase 7 で PMLE 4 技術 (BQML / Dataflow Flex Template / TreeSHAP Explainability / Monitoring SLO + burn-rate / Composer-managed BQ monitoring query) + Cloud Composer 本線 DAG (`infra/terraform/modules/composer/` + `pipeline/dags/` の 3 DAG) + Vertex AI Feature Store + Vertex Vector Search を **本 phase 配下に集約**。引き算チェーン (親 README §4) で Phase 6 / 5 / 4 / 3 / 2 / 1 を後方派生。詳細は docs/01 §0 / §3
- **学習 vs 推論**: 学習は Vertex AI Pipelines、推論は GKE `search-api` + KServe InferenceService (`property-encoder` / `property-reranker`)。モデルは cluster-local HTTP で `KServeEncoder` / `KServeReranker` 経由

---

## 非負制約 (User 確認無しに変えない)

| 項目 | 値 |
|---|---|
| **題材 / ハイブリッド検索中核** | 不動産検索 (上位 20 件)、Meilisearch BM25 + Vertex Vector Search + ME5 + RRF + LightGBM LambdaRank の挙動 / `/search` デフォルト応答 |
| **親リポ非負制約** | GCP `mlops-dev-a` / `asia-northeast1` / Python 3.12 / uv workspace / Terraform 1.9+ / WIF (SA Key 禁止) / 10 SA 最小権限分離 |
| **default feature flag** | `SEMANTIC_BACKEND` / `LEXICAL_BACKEND` / `BQML_POPULARITY_ENABLED` は default で Phase 5/6 挙動を維持 (`bq` / `meili` / `false`) |
| GKE Autopilot | `asia-northeast1` リージョナル、Gateway API + Workload Identity 既定有効 |
| search-api Deployment | `requests=500m/1Gi`, `limits=2/2Gi`, `minReplicas=1 maxReplicas=10` (HPA CPU 70% / Mem 80%) |
| KServe 認可境界 | NetworkPolicy で search → kserve-inference の in-cluster アクセスのみ許可 |
| Service Account | Phase 6 の 10 SA を GKE KSA (search/search-api, kserve-inference/encoder, kserve-inference/reranker) に Workload Identity bind |

---

## Feature parity invariant (6 ファイル同 PR 原則)

Phase 6 から継承。特徴量を追加 / 変更するとき、以下 6 つを **必ず同じ PR で揃える**:

1. `pipeline/data_job/dataform/features/property_features_daily.sqlx`
2. `ml/data/feature_engineering/ranker_features.py::build_ranker_features`
3. `ml/data/feature_engineering/schema.py::FEATURE_COLS_RANKER`
4. `infra/terraform/modules/data/main.tf` の `ranking_log.features` RECORD
5. `infra/sql/monitoring/validate_feature_skew.sql` の UNPIVOT
6. `infra/terraform/modules/vertex/main.tf::google_vertex_ai_feature_group_feature` × N

---

## ドキュメント衝突時の権威順位

`02_移行ロードマップ.md > docs/tasks/TASKS.md > 01_仕様と設計.md > README.md` (`docs/README.md §2`)。`CLAUDE.md` / `03_実装カタログ.md` は派生。`docs/tasks/TASKS.md` は `02_移行ロードマップ.md` の current-sprint 抜粋。

---

## 開発コマンド

全ターゲットは `make help`、生コマンド + PDCA STEP 詳細は [`docs/runbook/05_運用.md §1`](docs/runbook/05_運用.md)。**重要 target 早見**:

| target | 用途 |
|---|---|
| `make sync` / `make check` / `make check-layers` | uv workspace 同期 / CI 同等 (ruff + fmt + mypy + pytest) / Port-Adapter 境界 AST 検査 |
| `make deploy-all` / `make destroy-all` | Phase 7 の E2E デプロイ (14 step、初回は VVS attach 次第で 30-40 分) / Terraform 管理下の全破棄 (PDCA loop) |
| `make run-all` / `make run-all-core` / `make verify-all` | デプロイ後の E2E 検証 (`run-all-core` = check-layers → seed-test → ops-train-now → ops-livez/search/...) |
| `make tf-bootstrap` / `make tf-init` / `make tf-plan` / `make tf-validate` | Terraform 各 stage |
| `make api-dev` / `make train-smoke` / `make seed-test` | ローカル uvicorn / 合成データ学習 / PDCA smoke 用 5 件投入 |
| `make deploy-api` / `make deploy-kserve-models` / `make kube-creds` | search-api Cloud Build + rollout / KServe storageUri patch / kubeconfig 取得 |
| `make ops-*` | 本番 GCP 操作 (livez / search / ranking / feedback / accuracy-report / slo-status / promote-encoder / vertex-* 等) |
| `make bqml-train-popularity` / `make ops-slo-status` | Phase 6 PMLE 統合 (T1 BQML / T5 SLO + burn-rate) |

---

## GKE 固有の注意点

- **KServe URL**: `KSERVE_ENCODER_URL` / `KSERVE_RERANKER_URL` は cluster-local DNS (`http://<svc>.<ns>.svc.cluster.local/...`)。`infra/manifests/search-api/deployment.yaml` で ConfigMap に注入
- **KServe InferenceService の storageUri 更新**: `scripts/deploy/kserve_models.py` が Vertex Model Registry の `production` alias を引いて `kubectl patch` で書き換える。`make deploy-kserve-models` でラッパー
- **2 段階 apply**: 初回 Terraform apply は `-target=module.gke -target=module.iam -target=module.data` で cluster / IAM / storage を先行作成。provider.tf の kubernetes/helm provider が cluster 完成後に有効化されるため
- **Kubernetes Secret `meili-master-key`**: External Secrets Operator が Secret Manager から `search` namespace に自動同期する。値の投入自体は `gcloud secrets versions add meili-master-key` で行う
- **Vertex AI Endpoint は使わない**: encoder / reranker の推論は KServe 経由。`kserve_encoder_url` / `kserve_reranker_url` に cluster-local URL を設定する
- **PMLE 4 技術 + Feature Store + Composer は本 phase で本実装 (canonical)**: BQML popularity, Monitoring SLO + burn-rate, Dataflow streaming, TreeSHAP Explainability, Composer-managed BQ monitoring query, **Vertex AI Feature Store (Feature Group / Feature View / Feature Online Store)**, **Cloud Composer 3 本 DAG** はすべて本 phase 配下にあり、引き算で Phase 6 / 5 を後方派生する関係。Vertex Endpoint 部分は KServe に差し替え済み。Phase 7 固有: KServe pod から Feature Online Store を **Feature View 経由で** opt-in 参照する経路を追加

---

## Port / Adapter / DI 境界と make check

詳細は [`docs/architecture/01_仕様と設計.md §4`](docs/architecture/01_仕様と設計.md) (canonical) と [`docs/tasks/TASKS_ROADMAP.md §3`](docs/tasks/TASKS_ROADMAP.md)。設計優先順位は **DI > Port-Adapter > Clean > Domain**。

新規コード追加時の核ルール (詳細は上記 docs 参照):

- **Composition root** = `app/composition_root.py` のみ (`InfraBuilder` / `MlBuilder` / `SearchBuilder` 分割済)。`app/main.py` に DI 配線を書かない
- **DI**: handler は `Depends(get_container)` / `Depends(get_search_service)` で受け取る。`request.app.state.xxx` の `getattr` 禁止
- **1 Port 1 file** (`app/services/protocols/`)、**1 Adapter 1 file** (`app/services/adapters/`)、Noop / InMemory は `app/services/noop_adapters/`
- Service は Port のみ import、adapter import 禁止 / Schemas (`app/schemas/`) は SDK / lightgbm import 禁止 / Middleware は `google.cloud` import 禁止
- ML / Pipeline は `ml/<feature>/{ports,adapters}/`、`pipeline/<verb>_job/{ports,adapters}/` 構造
- 新 Port / service / handler / mapper / middleware / fake は `scripts/ci/layers.py` の RULES / DIRECTORY_RULES に追加

---

## 書き方

`docs/README.md §4` 書き方ルールに従う:
- 日本語で書く。英単語は技術用語としてそのまま
- コマンドは `make` ターゲット優先
- 識別子は固有名を使う (`<foo>` でぼかさない)
- STEP / 番号付きリストは上から叩けば成立する順序で書く
- 推測で書かない
