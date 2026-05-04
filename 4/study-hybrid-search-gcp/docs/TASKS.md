# TASKS.md (Phase 4)

`docs/02_移行ロードマップ.md` (長期 backlog/index) の current-sprint 抜粋。

## 現在の目的

Phase 4 = Phase 3 のローカル検索を **Cloud Run / BigQuery / GCS / Pub/Sub / Terraform / WIF / Secret Manager** へ移し替え、GCP serverless 実行基盤を学ぶフェーズ。**完了済 (アーカイブ運用)**。検索中核は `Meilisearch + BigQuery VECTOR_SEARCH + ME5 + RRF + LightGBM LambdaRank`。

## 今回の作業対象

新規作業は基本無し。以下の保守目的のみ:

- `02_移行ロードマップ.md §5 残タスク` に列挙された軽微整理
- `make check` (ruff + mypy strict + pytest) で回帰しない範囲の追従

## 今回はやらない

- Vertex AI Pipelines / Endpoints / Model Registry / Feature Group / Monitoring (Phase 5 へ)
- BQML / Dataflow / Monitoring SLO / Explainable AI (Phase 6 へ)
- GKE / KServe / Gateway API (Phase 7 へ)

## 完了条件 (達成済)

- [x] `make check` (CI 同等) 通過
- [x] Cloud Run Service (`search-api`) + Cloud Run Jobs (training / embedding) 起動
- [x] BigQuery `VECTOR_SEARCH` で semantic 経路成立
- [x] Terraform 1.9+ で IaC 化、WIF で SA Key 不使用
- [x] Secret Manager から Meilisearch master key 注入
- [x] Cloud Scheduler + Eventarc + Cloud Function で軽量 orchestration

## 実装済

- [x] Cloud Run Service / Jobs
- [x] BigQuery feature table / view (Phase 5 Feature Store の入力源)
- [x] BigQuery `VECTOR_SEARCH` (Phase 5 で Vertex Vector Search に置換)
- [x] GCS モデル成果物保管
- [x] Pub/Sub ranking log / feedback 非同期化
- [x] Terraform module 群 (data / iam / run / pubsub 等)
- [x] WIF 認証 (CI/CD)
- [x] Secret Manager 統合

## 未実装 / 残タスク

`02_移行ロードマップ.md §5` 抜粋:

- [ ] `docs/03_実装カタログ.md` の旧命名 / 過剰説明の整理 (必要に応じて)
- [ ] `docs/04_運用.md` の旧 Phase 表現の圧縮 (必要に応じて)
- [ ] ローカルで回せる範囲のテスト追従 (必要に応じて)

優先度低 (Phase 5 以降の作業を妨げない)。

## 次 Phase

`5/study-hybrid-search-vertex/` — Vertex AI 本番 MLOps 基盤 (Pipelines / Feature Store / Vector Search / Model Registry / Monitoring)。
