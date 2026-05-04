# study-hybrid-search-gke

**不動産ハイブリッド検索 × LightGBM LambdaRank** を GKE + KServe で serving する MLOps 学習リポジトリ。Phase 5 (Vertex AI プリミティブ) を継承しつつ、**serving 層のみを GKE / KServe に差し替える** 最小差分版。

> **スコープ**: 不動産検索 (クエリ文 + フィルタ → ランキング上位 20 件) のみ。
> **Phase 5 からの差分**: `search-api` (Cloud Run → GKE Deployment + Gateway) / encoder / reranker (Vertex Endpoint → KServe `InferenceService`)。Pipelines / **Vertex AI Feature Store (Feature Group / Feature View / Feature Online Store)** (Phase 5 必須を継承) / Model Registry / **Vertex Vector Search** (Phase 5 で BQ `VECTOR_SEARCH` から置換、本 Phase でも継承) / Meilisearch は据え置き。Phase 7 固有として KServe から Feature Online Store を opt-in 参照する経路を追加。

本 README は「機能の簡易説明 + 各ドキュメントへのリンク」だけを扱う (`docs/README.md` §1 の規約に従う)。環境構築・運用・実装詳細は下記 **§ ドキュメント** の各ファイルへ。

## アーキテクチャ

```
raw.properties (upstream ETL)
  └─ Dataform ─> feature_mart.properties_cleaned
                 feature_mart.property_features_daily (ctr / fav_rate / inquiry_rate)
  └─ Vertex AI KFP `property-search-embed` pipeline ─> Vertex Vector Search index (`property-embeddings`、ME5 ベクトル serving index。生成履歴・メタデータは BigQuery 側に残す)
  └─ Vertex AI KFP `property-search-train` pipeline ─> GCS + mlops.training_runs + Vertex Model Registry

         └─ GKE Deployment `search-api` (FastAPI, in namespace `search`)
              ├─ /search   KServe encoder + Meilisearch (BM25) + Vertex Vector Search match endpoint → RRF → KServe reranker
              │             └─ Pub/Sub "ranking-log"    ─> BQ Subscription ─> mlops.ranking_log
              ├─ /feedback └─ Pub/Sub "search-feedback" ─> BQ Subscription ─> mlops.feedback_events
              └─ /jobs/check-retrain (Cloud Scheduler 04:00 JST → Gateway HTTPS endpoint)

         └─ KServe InferenceService `property-encoder` / `property-reranker` (namespace `kserve-inference`)
              ├─ property-encoder  multilingual-e5 Python predictor (storageUri = Model Registry artifact)
              └─ property-reranker MLServer LightGBM runtime     (storageUri = Model Registry artifact)

  └─ Cloud Run Service `meili-search` (GCS FUSE `/meili_data` mount、Phase 5 から据え置き)
  └─ Scheduled Query 05:00 JST `property_feature_skew_check` ─> mlops.validation_results
```

## ディレクトリ

| パス | 役割 |
|---|---|
| `infra/terraform/` | Terraform — `data` / `gke` / `iam` / `kserve` / `meilisearch` / `messaging` / `monitoring` / `slo` / `streaming` / `vertex` モジュール (BQ / GCS / Pub/Sub / GKE Autopilot / KServe Helm / Vertex Pipelines / Scheduler / WIF / SLO) |
| `infra/manifests/` | K8s manifests — search-api 系 (Deployment / Service / Gateway / HPA / PodMonitoring / ConfigMap example) + KServe 系 (encoder / reranker / reranker-explain / PodMonitoring) + `policies/` (IAP / NetworkPolicy) + 統合 `kustomization.yaml` |
| `pipeline/data_job/dataform/` | Dataform — `properties_cleaned` + `property_features_daily` + assertions + `monitoring/ranking_rank_diff_daily.sqlx` |
| `app/` | FastAPI search-api。`composition_root.py` + `container/{infra,ml,search}.py` で DI、`api/{handlers,mappers,middleware,routes}/`、`services/{protocols,adapters,noop_adapters}/`、`domain/`、`schemas/`、`settings/`、Jinja2 `templates/` + `static/` |
| `ml/{common,data,training,evaluation,registry,serving,streaming}/` | 共有コード + ML pipeline 部品 — `BigQueryEmbeddingStore` / `build_ranker_features` / ranking metrics / logging / gcs。`registry`・`serving`・`streaming`・`training` は `ports/` + `adapters/` 構造 |
| `pipeline/{data_job,training_job,evaluation_job,batch_serving_job,workflow}/` | KFP エントリポイント。`data_job` / `training_job` は `ports/` + `adapters/` + `components/` 構造、`workflow/` でコンパイル & 投入 |
| `scripts/` | 運用コマンド群。`setup/` (deploy_all / destroy_all / tf_* / doctor / seed_minimal / setup_model_monitoring / create_schedule / upload_encoder_assets / `local_hybrid`) / `deploy/` (api_gke / kserve_models / monitor) / `ops/` (livez / search / ranking / feedback / promote / vertex_* / slo_status 他) / `ci/` (layers / sync_dataform) / `bqml/` (train_popularity) / `sql/` (BQ 運用クエリ 4 本) |
| `monitoring/` | feature skew Scheduled Query SQL (`validate_feature_skew.sql`) |
| `.github/workflows/` | `ci.yml` (ruff/fmt/mypy/pytest) + `terraform.yml` + `deploy-api.yml` (kubectl set image) + `deploy-encoder-image.yml` / `deploy-trainer-image.yml` / `deploy-reranker-image.yml` / `deploy-pipeline.yml` / `deploy-dataform.yml` |
| `docs/` | 仕様と設計・移行ロードマップ (本体 + Port-Adapter-DI + 切り替え基盤)・実装カタログ・運用・`教育資料/` (スライド / ナレーション台本 / デモシナリオ / 図解) |

ファイル単位の一言コメントは [`docs/architecture/03_実装カタログ.md §2`](docs/architecture/03_実装カタログ.md)。

## 設計ハイライト

詳細は [`docs/tasks/TASKS_ROADMAP.md`](docs/tasks/TASKS_ROADMAP.md) と [`docs/architecture/01_仕様と設計.md`](docs/architecture/01_仕様と設計.md)。

- **Phase 5 からの差分**: serving 層のみ GKE + KServe に移行。Pipelines / **Vertex AI Feature Store (Feature Group / Feature View / Feature Online Store)** (Phase 5 必須を継承) / Model Registry / **Vertex Vector Search** (Phase 5 で BQ `VECTOR_SEARCH` から置換、本 Phase でも継承) / Meilisearch は **差分ゼロで維持**。Phase 7 固有として KServe から Feature Online Store を opt-in 参照する経路を追加
- **Port / Adapter 設計**: `app.services.protocols` の `EncoderClient` / `RerankerClient` 実装を `VertexEndpointEncoder/Reranker` → `KServeEncoder/Reranker` に差し替えただけ (core / services / ports は無変更)
- **認可境界**: Gateway API + IAP + NetworkPolicy で Cloud Run の `--no-allow-unauthenticated` + IAM 相当を再現
- **Workload Identity**: Phase 6 の 10 SA をそのまま GKE KSA にバインドして使い回す (新規 SA は追加しない)
- **予測分布 drift 検知は縮退**: Vertex Model Monitoring v2 は Vertex Endpoint 前提なので Phase 7 (serving 層 = KServe) では失う (復活は KServe payload logging + 自前 drift 計算の別タスクに分離)
- **固定値**: プロジェクト `mlops-dev-a` / リージョン `asia-northeast1` / Python 3.12 / uv / Terraform 1.9

## Live 検証の境界（Composer / V5）

[`docs/tasks/TASKS.md`](docs/tasks/TASKS.md) が sprint の正本。**狭いゲート定義**は [`docs/runbook/04_検証.md`](docs/runbook/04_検証.md) §0、**クライアント向けの最低説明**は TASKS の **死守ライン**（Composer 経由の再学習 E2E + `/search` 健全性）。

| 優先 | 意味 |
|---|---|
| **死守** | `check_retrain` だけでなく、`submit_train_pipeline` → `wait_train_succeeded` → gate / promote（または意図どおり skip）まで live で踏む。**再学習後に `/search` が 200 で 3 成分が壊れていない**ことまで（TASKS チェックリスト） |
| **それ以外** | V4（2 周目 deploy）→ V6（parity）→ V3（destroy）は **死守の後**。同列に並べない |

実装メモ: Run 4 は `submit_train_pipeline` が **failed**（argv の shell 形リテラル + `dist/pipelines`）。**V5-8** で `scripts.ops.submit_train_pipeline` + `/tmp/pipelines`。runner image の **再 build・push** と DAG upload が前提。

## デプロイ

`main` へのマージで path filter に応じて以下が走る:

| 変更 | 反応するワークフロー | 動作 |
|---|---|---|
| `infra/terraform/**` | `terraform.yml` | plan (PR コメント) → push で apply |
| `app/**`, `ml/**`, `pyproject.toml`, `uv.lock` | `deploy-api.yml` | Docker build → Artifact Registry → `kubectl set image deployment/search-api` (manifest 変更は反応せず、`kubectl apply -k` 別運用) |
| `ml/serving/**`, `ml/common/**`, `ml/registry/**`, `infra/run/services/encoder/**` | `deploy-encoder-image.yml` | Docker build → push `property-encoder` image (KServe / Vertex Pipelines で使用) |
| `ml/training/**`, `ml/common/**`, `ml/data/**`, `ml/registry/**` | `deploy-trainer-image.yml` | Docker build → push `property-trainer` image (KFP train job で使用) |
| `ml/serving/**`, `ml/data/feature_engineering/**`, `ml/registry/**`, `infra/run/services/reranker/**` | `deploy-reranker-image.yml` | Docker build → push `property-reranker` image (KServe で使用) |
| `pipeline/{data_job,training_job,evaluation_job}/**` | `deploy-pipeline.yml` | KFP templates compile → upload to GCS |
| `pipeline/data_job/dataform/**` | `deploy-dataform.yml` | `scripts.ci.sync_dataform` → `dataform compile` → Dataform API へ compilationResults POST |

認証はすべて WIF。

## ドキュメント

初めてこのリポジトリに触る人は、まず [`docs/runbook/05_運用.md §1 PDCA メインフロー`](docs/runbook/05_運用.md) を上から叩く (`make deploy-all` → `make run-all` → `make destroy-all`)。

local で hybrid 検索まで動かす標準手順は `make api-dev-hybrid`。このターゲットは `scripts/setup/local_hybrid.py` を呼び、非秘密値は `env/config/setting.yaml`、秘密値は `env/secret/credential.yaml` または Secret Manager から解決して、local encoder / reranker / app をまとめて起動する。

| ドキュメント | 目的 | 主な読者 |
|---|---|---|
| [`docs/README.md`](docs/README.md) | ドキュメント運用ルール (役割 / 権威順位 / 更新規約 / 書き方) | 文書を触る人全員 |
| [`docs/architecture/01_仕様と設計.md`](docs/architecture/01_仕様と設計.md) | 機能仕様 + アーキテクチャ設計 | LLM / 設計レビュー |
| [`docs/tasks/TASKS_ROADMAP.md`](docs/tasks/TASKS_ROADMAP.md) | **本リポジトリの決定的仕様** の母艦。現状はサブドキュメントに分割中 (下 2 つ) | LLM / 開発者 |
| [`docs/02_移行ロードマップ-Port-Adapter-DI.md`](docs/02_移行ロードマップ-Port-Adapter-DI.md) | Phase 7 の Port / Adapter / DI 整備履歴と層境界ルール | LLM / 開発者 |
| [`docs/02_移行ロードマップ切り替え基盤.md`](docs/02_移行ロードマップ切り替え基盤.md) | Vertex Endpoint → KServe 切り替えの差分仕様 | LLM / 開発者 |
| [`docs/architecture/03_実装カタログ.md`](docs/architecture/03_実装カタログ.md) | 実装カタログ (ディレクトリ / ファイル / DB テーブル / API / GCP / Terraform) | 新規参加者 / LLM |
| [`docs/runbook/05_運用.md`](docs/runbook/05_運用.md) | 環境構築 + 定常運用 + インシデント対応 + ロールバック | 新規参加者 / 運用担当 |
| [`docs/教育資料/`](docs/教育資料/) | スライド / ナレーション台本 / デモシナリオ / 図解 (`assets/*.svg`) | 学習・デモ担当 |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code 向け作業ガイド (非負制約 / 参照リポジトリ / feature-parity invariant) | Claude Code |

ドキュメントが互いに矛盾したときの勝者は `docs/tasks/TASKS_ROADMAP.md` (詳細は `docs/README.md §2` 権威順位)。

## 品質ステータス

`make check` 全工程 PASS 目標 — ruff / ruff format / mypy strict / pytest。
`make check-layers` で AST ベースの Port / Adapter 境界違反検知も PASS させる。
`make tf-validate` PASS (offline)。
