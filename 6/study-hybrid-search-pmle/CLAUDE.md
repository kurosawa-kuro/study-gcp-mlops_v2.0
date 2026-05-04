# CLAUDE.md

本リポジトリ (`7/study-hybrid-search-gke`) で作業する Claude Code 向けのガイド。**Phase 7 は Phase 6 (`6/study-hybrid-search-pmle/`) の PMLE 技術統合をそのまま継承した上で、Serving 層のみを Vertex AI Endpoint から GKE + KServe InferenceService に差し替えた Draft フェーズ**。中核コード (不動産ハイブリッド検索) は変えず、encoder / reranker の推論呼び出しを cluster-local HTTP に切り替える。

ドキュメント全般の運用規約は [`docs/README.md`](docs/README.md)、スコープの決定権は [`docs/02_移行ロードマップ.md`](docs/02_移行ロードマップ.md)。本 CLAUDE.md はそれらに従属する。

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

## 最初に読むもの (順番)

1. [`docs/02_移行ロードマップ切り替え基盤.md`](docs/02_移行ロードマップ切り替え基盤.md) — Phase 6 からの差分 (Serving 層のみ Vertex Endpoint → GKE + KServe)。母艦の [`docs/02_移行ロードマップ.md`](docs/02_移行ロードマップ.md) は backlog/index として維持し、本ファイルと下記 Port-Adapter-DI ファイルが暫定の決定仕様
2. [`docs/02_移行ロードマップ-Port-Adapter-DI.md`](docs/02_移行ロードマップ-Port-Adapter-DI.md) — Phase 7 で全面整備した DI / Port / Adapter / fakes / handlers / mappers の層境界ルール
3. [`docs/01_仕様と設計.md`](docs/01_仕様と設計.md) — 機能仕様 + アーキテクチャ設計 (Phase 6 から継承の PMLE 統合トピック含む)
4. [`docs/03_実装カタログ.md`](docs/03_実装カタログ.md) + [`docs/04_運用.md`](docs/04_運用.md) — 実装 / 運用詳細
5. `infra/manifests/` — search-api 系 (Deployment / Service / Gateway / HPA / PodMonitoring / ConfigMap example) + KServe 系 (encoder / reranker / reranker-explain / PodMonitoring) + `policies/` (IAP / NetworkPolicy) + 統合 `kustomization.yaml`

---

## hybrid-search-gke の設計テーゼ (題材: 不動産ハイブリッド検索)

- **題材**: 自由文クエリ + フィルタ → 物件ランキング上位 20 件。3 段構成 = (1a) Meilisearch BM25、(1b) **Vertex Vector Search** (ME5 ベクトル検索の本番 serving index + ANN。embedding 生成履歴・メタデータは BigQuery 側に残す)、(2) RRF 融合、(3) LightGBM `lambdarank` 再ランク
- **Phase 6 PMLE 技術 (BQML / Dataflow / Monitoring SLO + 補助 Explainable AI) を完全継承**。Phase 5 で導入された **Vertex AI Feature Store / Feature Group / Feature Online Store** と **Vertex Vector Search** も Phase 5 → 6 → 7 と継承(Phase 6 では Dataflow / Scheduled Query で Feature Store の入力生成・更新を強化)。Serving 層のみ GKE + KServe に差し替え。親 README §1 教材対象外と全 Phase 禁止技術 (Agent Builder / Gemini RAG / Model Garden / Vizier / W&B / Looker Studio / Doppler) は本リポでも一切扱わない
- **学習 = Vertex AI Pipelines (`embed_pipeline` + `train_pipeline`) / 推論 = GKE Deployment (`search-api`) + KServe InferenceService (`property-encoder` / `property-reranker`)**。モデルは API コンテナへ同梱せず、`search-api` は `KServeEncoder` / `KServeReranker` を通して cluster-local HTTP で推論を委譲する

---

## 非負制約 (User 確認無しに変えない)

### 不変 — 絶対に変えない

| 項目 | 値 |
|---|---|
| **題材 / ドメイン** | 不動産ハイブリッド検索 (クエリ + フィルタ → 物件ランキング上位 20 件) |
| **ハイブリッド検索中核** | Meilisearch BM25 (lexical) + **Vertex Vector Search** + multilingual-e5 (semantic) + RRF 融合 + LightGBM LambdaRank (rerank) の挙動 / データフロー / デフォルト `/search` レスポンス(2026-05-01 改定で BQ `VECTOR_SEARCH` から Vertex Vector Search に置換 — 仕様 docs 先行、実装は別 PR で追従) |
| **親リポ非負制約** | GCP プロジェクト `mlops-dev-a` / リージョン `asia-northeast1` / Python 3.12 / uv workspace / Terraform 1.9+ / WIF (SA Key 禁止) / 10 SA 最小権限分離 |
| **default feature flag 値** | Phase 6 から継承した flag (`SEMANTIC_BACKEND` / `LEXICAL_BACKEND` / `BQML_POPULARITY_ENABLED` 等) は default で Phase 5/6 挙動を維持 (`bq` / `meili` / `false`) |

| 項目 | 値 | 理由 |
|---|---|---|
| GCP プロジェクト | `mlops-dev-a` | 固定 |
| リージョン | `asia-northeast1` | 固定 |
| Python | 3.12 | `pyproject.toml` |
| パッケージ管理 | `uv` (pip / poetry 不可) | workspace 採用 |
| IaC | Terraform 1.9+ | |
| GKE Autopilot | `asia-northeast1` リージョナル、Gateway API + Workload Identity 既定有効 | Phase 7 serving 層の実行基盤 |
| search-api Deployment | `requests=500m/1Gi`, `limits=2/2Gi`, `minReplicas=1 maxReplicas=10` (HPA CPU 70% / Mem 80%) | |
| KServe 認可境界 | NetworkPolicy で search namespace → kserve-inference namespace の in-cluster アクセスのみ許可 | |
| Service Account | Phase 6 の 10 SA 分離を継承。GKE KSA (search/search-api, kserve-inference/encoder, kserve-inference/reranker) に Workload Identity で bind | |

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

`docs/README.md §2` に従う:

```
02_移行ロードマップ.md > 01_仕様と設計.md > README.md
```

`CLAUDE.md` と `03_実装カタログ.md` は上位 3 者から派生する従属ドキュメント。

**現状の補足**: `docs/02_移行ロードマップ.md` は backlog/index として維持し、詳細仕様は以下のサブドキュメントに分割済み:
- `docs/02_移行ロードマップ-Port-Adapter-DI.md` — Port / Adapter / DI 層境界
- `docs/02_移行ロードマップ切り替え基盤.md` — Serving 層差し替え (Vertex → KServe) の差分

権威順位はサブドキュメントを「母艦と等価」と扱う。母艦が再構成された場合はそちらに統合する。

---

## 開発コマンド

生コマンドは `docs/04_運用.md §1` の STEP、全ターゲットは `make help`。`make check` でローカル CI 同等 (ruff / ruff format / mypy strict / pytest) を走らせる。

| target | 用途 |
|---|---|
| `make doctor` | 前提ツール到達確認 |
| `make sync` | uv workspace + dev group 同期 |
| `make check` | ruff + fmt-check + mypy + pytest (CI 同等) |
| `make check-layers` | AST で Port/Adapter 境界違反を検出 (`scripts/ci/layers.py`) |
| `make sync-dataform-config` | `pipeline/data_job/dataform/workflow_settings.yaml` を `env/config/setting.yaml` から再生成 |
| `make train-smoke` / `make train-smoke-persist` | 合成データで LightGBM LambdaRank 学習 (GCP 認証不要) / 学習後にモデルファイル保存 |
| `make api-dev` | ローカル uvicorn (`ENABLE_SEARCH=false` 既定) |
| `make tf-validate` / `make tf-fmt` / `make tf-fmt-fix` | オフライン terraform validate / fmt --check / fmt 書き込み |
| `make tf-bootstrap` / `make tf-init` / `make tf-plan` | Phase 0 (API 有効化 + tfstate バケット) / preflight 付き init / plan (`tfplan` 保存) |
| `make setup-model-monitoring` / `make setup-pipeline-schedule` | Vertex Model Monitoring / Pipeline schedule 設定の resolved payload を出力 |
| `make deploy-all` | **Phase 7 の E2E デプロイ** — `scripts.setup.deploy_all` 経由で 7 step (tf-bootstrap → tf-init → WIF 復元 → sync-dataform-config → tf-plan → tf apply → deploy-api) を順に実行 |
| `make destroy-all` | Terraform 管理下の全リソース破棄 (BQ table `deletion_protection` を `-target` で先に解除)。`deploy-all` とペアで PDCA loop |
| `make run-all` / `make run-all-core` / `make verify-all` | デプロイ後の E2E 検証 (`run-all-core` = check-layers → seed-test → ops-train-now → ops-livez/search/search-components/feedback/ranking/label-seed → ops-daily → ops-accuracy-report)。`run-all` は `ops-run-all-monitor` を介して実行 |
| `make seed-test` / `make seed-test-clean` | PDCA smoke 用 5 件の test property 投入 / 削除 |
| `make kube-creds` | 対象 GKE Autopilot クラスタの kubeconfig を取得 |
| `make deploy-api` | Cloud Build → Artifact Registry → `kubectl set image` で rollout (単独) |
| `make deploy-kserve-models` | Vertex Model Registry の `production` alias artifact URI を引いて KServe InferenceService を更新 |
| `make ops-api-url` | search-api Gateway の external URL を表示 |
| `make ops-reload-api` | `kubectl rollout restart deployment/search-api` で rolling restart |
| `make ops-deploy-monitor` / `make ops-run-all-monitor` | `scripts.deploy.monitor` で `deploy-all` / `run-all-core` を実行しリアルタイムでステップ / Cloud Build 停滞を監視 (ログは `logs/deploy-monitor/`) |
| `make ops-slo-status` | Phase 6 T5: SLO compliance + burn-rate を表示 |
| `make bqml-train-popularity` | Phase 6 T1: BQML property-popularity model 学習 |
| `make ops-promote-encoder` / `make ops-promote-reranker` | Vertex Model Registry の `production` alias を encoder / reranker に付け替え (`MODEL_ID=N` または `VERSION_ID=N` + `APPLY=1`) |
| `make ops-vertex-*` | Vertex AI 各サーフェス単体スモーク (models-list / pipeline-status / explain / monitoring / feature-group)。`make ops-vertex-all` で全部チェーン |
| `make ops-*` | 本番 GCP 操作 (livez / search / search-components / ranking / feedback / label-seed / check-retrain / accuracy-report / daily / skew-* / search-volume / runs-recent / bq-scan-top / train-now / pipeline-run 等) |

---

## GKE 固有の注意点

- **KServe URL**: `KSERVE_ENCODER_URL` / `KSERVE_RERANKER_URL` は cluster-local DNS (`http://<svc>.<ns>.svc.cluster.local/...`)。`infra/manifests/search-api/deployment.yaml` で ConfigMap に注入
- **KServe InferenceService の storageUri 更新**: `scripts/deploy/kserve_models.py` が Vertex Model Registry の `production` alias を引いて `kubectl patch` で書き換える。`make deploy-kserve-models` でラッパー
- **2 段階 apply**: 初回 Terraform apply は `-target=module.gke -target=module.iam -target=module.data` で cluster / IAM / storage を先行作成。provider.tf の kubernetes/helm provider が cluster 完成後に有効化されるため
- **Kubernetes Secret `meili-master-key`**: External Secrets Operator が Secret Manager から `search` namespace に自動同期する。値の投入自体は `gcloud secrets versions add meili-master-key` で行う
- **Vertex AI Endpoint は使わない**: encoder / reranker の推論は KServe 経由。`kserve_encoder_url` / `kserve_reranker_url` に cluster-local URL を設定する
- **Phase 6 PMLE 技術はそのまま**: BQML popularity, SLO, Dataflow streaming は Phase 6 と同一実装。Vertex Endpoint 部分だけ KServe に差し替え済み

---

## Port / Adapter / DI 境界と make check

Phase 7 では Phase 6 から継承した Port-Adapter 構造を **DI 最優先で全面整備しなおした**。詳細は [`docs/02_移行ロードマップ-Port-Adapter-DI.md`](docs/02_移行ロードマップ-Port-Adapter-DI.md) と [`docs/01_仕様と設計.md §4`](docs/01_仕様と設計.md)。設計優先順位は **DI > Port-Adapter > Clean > Domain**。

### 新しいコードを追加するときの基準

- **Composition root** (`app/composition_root.py`): 全 adapter / service の組み立ては `ContainerBuilder.build()` 内で行う。本体は `app/container/{infra,ml,search}.py` の `InfraBuilder` / `MlBuilder` / `SearchBuilder` に分割済み (`_optional_adapter.py` で adapter import の遅延ガード)。`app/main.py` には DI 配線を書かない
- **DI**: handler は `Depends(get_container)` または `Depends(get_search_service)` 等で受け取る。`request.app.state.xxx` の `getattr` 使用禁止
- **Port (Protocol)**: `app/services/protocols/<name>.py`。**1 Protocol 1 file** (Phase B-1 ルール)。`app/` は `protocols/`、`ml/` / `pipeline/` は `ports/` を canonical 名として使い分ける
- **Adapter (production)**: `app/services/adapters/<name>.py`。**1 Adapter 1 file**。外部 SDK 依存はここでのみ
- **Fake (production noop / in-memory)**: `app/services/noop_adapters/<name>.py`。Noop / InMemory はここに集約 (test stub は `tests/fakes/`)
- **Domain**: `app/domain/`。Candidate / SearchFilters / SearchInput / SearchOutput など
- **Schemas**: `app/schemas/`。FastAPI 入出力 Pydantic モデル (`search.py` / `model.py`)。SDK / lightgbm import 禁止 (layers.py の RULE 対象)
- **Service**: `app/services/<name>_service.py`。Port のみ import、adapter import 禁止。HTTP 詳細を持たない
- **Router**: `app/api/routers/<endpoint>_router.py`。1 endpoint 1 file (現状: `search` / `feedback` / `health` / `model` / `retrain` / `ui`)
- **Mapper**: `app/api/mappers/<endpoint>_mapper.py`。Pydantic ↔ domain 変換 1 箇所
- **Middleware**: `app/api/middleware/<name>.py` (現状: `request_logging.py`)。`google.cloud` import 禁止
- **ML / Pipeline**: `ml/<feature>/{ports,adapters}/`、`pipeline/<verb>_job/{ports,adapters}/`。`ml/{registry,serving,streaming,training}` 配下と `pipeline/{data_job,training_job}` 配下に Port / Adapter を持つ (`evaluation_job` / `batch_serving_job` は `main.py` のみのシンプル構成)
- **境界検知**: `scripts/ci/layers.py` の RULES (per-file) と DIRECTORY_RULES (auto-discover) に新 Port / service / handler / mapper / middleware / fake / ml port / pipeline port を追加

---

## 書き方

`docs/README.md §4` 書き方ルールに従う:
- 日本語で書く。英単語は技術用語としてそのまま
- コマンドは `make` ターゲット優先
- 識別子は固有名を使う (`<foo>` でぼかさない)
- STEP / 番号付きリストは上から叩けば成立する順序で書く
- 推測で書かない
