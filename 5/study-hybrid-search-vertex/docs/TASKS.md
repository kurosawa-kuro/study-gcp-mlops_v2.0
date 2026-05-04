# TASKS.md (Phase 5)

`docs/02_移行ロードマップ.md` (長期 backlog/index) の current-sprint 抜粋。

## 現在の目的

Phase 5 = Phase 4 の GCP serverless 構成を土台に **Vertex AI Pipelines / Endpoints / Model Registry / Vertex AI Feature Store (Feature Group / Feature View / Feature Online Store) / Vertex Vector Search / Model Monitoring** を実コードへ統合する Vertex 標準 MLOps 学習フェーズ。**完了済 (アーカイブ運用)**。検索中核は `Meilisearch + Vertex Vector Search + ME5 + RRF + LightGBM LambdaRank` (Phase 4 の BQ `VECTOR_SEARCH` 経路は本 Phase で Vertex Vector Search に置換 — 2026-05-01 改定)。

## 今回の作業対象

新規作業は基本無し。以下の保守目的のみ:

- `02_移行ロードマップ.md §5 残タスク` に列挙された軽微整理
- `make check` で回帰しない範囲の追従

## 今回はやらない

- BQML / Dataflow / Monitoring SLO / Explainable AI (Phase 6 へ)
- Cloud Composer 本線 orchestration (Phase 6 へ — Phase 5 では Phase 4 軽量経路を継続)
- GKE / KServe / Gateway API (Phase 7 へ)
- 全 Phase 共通禁止技術 (Agent Builder / Discovery Engine / Gemini RAG / Model Garden / Vizier / W&B / Looker Studio / Doppler)

## 完了条件 (達成済)

- [x] `make check` 通過
- [x] 5A: Pipelines / Registry / Endpoint
- [x] 5B: Feature Store (Feature Group / Feature View / Feature Online Store)
- [x] 5C: Vertex Vector Search (Phase 4 BQ `VECTOR_SEARCH` を置換)
- [x] 5D: Monitoring / Dataform / Scheduled feature refresh

## 実装済 (5A〜5D)

### 5A: Pipelines / Registry / Endpoint
- [x] Vertex AI Pipelines (`embed_pipeline` + `train_pipeline`)
- [x] Vertex AI Endpoints (encoder / reranker 推論の外出し)
- [x] Model Registry + version 昇格 (`production` alias)

### 5B: Feature Store
- [x] Feature Group / Feature View / Feature Online Store
- [x] training (`pipeline/`) と serving (`app/`) で同一 feature 経路 (training-serving skew 防止)
- [x] BQ feature table / view (Phase 4) を入力源に格上げ

### 5C: Vertex Vector Search
- [x] ME5 ベクトル検索の本番 serving index (ANN)
- [x] embedding 生成履歴・メタデータの正本は BigQuery 側に維持
- [x] `/search` semantic 経路を Vertex Vector Search に切替

### 5D: Monitoring / Dataform / Scheduled refresh
- [x] Vertex Model Monitoring v2 (drift 検知)
- [x] Dataform で feature 更新パイプライン
- [x] Scheduled feature refresh

## 未実装 / 残タスク

`02_移行ロードマップ.md §5` 抜粋:

- [ ] `docs/03_実装カタログ.md` の現行スコープへの圧縮 (必要に応じて)
- [ ] `docs/04_運用.md` の旧命名 / 旧手順の整理 (必要に応じて)
- [ ] ローカルで回せる範囲のテスト追従 (必要に応じて)

優先度低 (Phase 6 以降の作業を妨げない)。

## 次 Phase

`6/study-hybrid-search-pmle/` — Phase 5 完成系に PMLE 追加技術 (BQML / Dataflow / Explainable AI / Monitoring SLO) を統合 + Cloud Composer を本線 orchestration として導入。
