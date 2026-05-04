# TASKS.md (Phase 3)

`docs/02_移行ロードマップ.md` (長期 backlog/index) の current-sprint 抜粋。

## 現在の目的

Phase 3 = **Meilisearch + multilingual-e5 + Redis + LightGBM LambdaRank** を使ったローカル不動産ハイブリッド検索の学習フェーズ。**完了済 (アーカイブ運用)**。検索 / 特徴量 / 学習 / 評価の流れを Docker Compose で一巡させる。

## 今回の作業対象

新規作業は基本無し。以下の保守目的のみ:

- `02_移行ロードマップ.md §5 残タスク` に列挙された軽微整理
- `make test` / `make check-layers` / `make verify-pipeline` で回帰しない範囲の追従

## 今回はやらない

- Cloud Run / BigQuery / GCS / Pub/Sub / Terraform / WIF / Secret Manager (Phase 4 へ)
- Vertex AI Pipelines / Endpoints / Model Registry / Feature Group / Monitoring (Phase 5 へ)
- BQML / Dataflow / Monitoring SLO / Explainable AI (Phase 6 へ)
- GKE / KServe / Gateway API (Phase 7 へ)

## 完了条件 (達成済)

- [x] `make ops-bootstrap` / `make ops-daily` / `make ops-weekly` 系のローカルフロー
- [x] `make test` / `make check-layers` / `make verify-pipeline` 通過
- [x] lexical / semantic / rerank の 3 役を分離した構成

## 実装済

- [x] Meilisearch BM25 検索 (Adapter)
- [x] multilingual-e5 semantic 類似度
- [x] Redis キャッシュ
- [x] LightGBM LambdaRank 再ランキング
- [x] PostgreSQL ローカル永続化
- [x] Docker Compose 起動 (PostgreSQL / Redis / Meilisearch)
- [x] Port/Adapter 境界 (`scripts/ci/layers.py` 検証)

## 未実装 / 残タスク

`02_移行ロードマップ.md §5` 抜粋:

- [ ] `docs/03_実装カタログ.md` の Cloud 前提残骸の圧縮 (必要に応じて)
- [ ] 教育資料の制作メモ類で後続 Phase 前提の説明を整理 (必要に応じて)

優先度低 (Phase 4 以降の作業を妨げない)。

## 次 Phase

`4/study-hybrid-search-gcp/` — GCP serverless 実行基盤への移行 (Cloud Run / BigQuery / Terraform / WIF / Secret Manager)。
