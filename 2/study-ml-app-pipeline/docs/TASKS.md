# TASKS.md (Phase 2)

`docs/02_移行ロードマップ.md` (長期 backlog/index) の current-sprint 抜粋。

## 現在の目的

Phase 2 = Phase 1 の California Housing 回帰を土台に、**FastAPI / lifespan DI / Port-Adapter / job 分離** を導入し、依存方向と DI の責務分担を整理するフェーズ。**完了済 (アーカイブ運用)**。

## 今回の作業対象

新規作業は基本無し。以下の保守目的のみ:

- `02_移行ロードマップ.md` の不変ルールに反しない範囲のドキュメント / コードの軽微修正
- `make test` で回帰しない範囲の追従

## 今回はやらない

- Meilisearch / multilingual-e5 / Redis / LightGBM LambdaRank / 不動産検索ドメイン (Phase 3 へ)
- Cloud Run / BigQuery / GCS / Pub/Sub / Terraform / WIF / Secret Manager (Phase 4 へ)
- Vertex AI Pipelines / Endpoints / Model Registry / Monitoring (Phase 5 へ)
- BQML / Dataflow / RAG / Explainable AI / SLO / GKE / KServe (Phase 6/7 へ)

## 完了条件 (達成済)

- [x] FastAPI で `/predict` API 起動
- [x] lifespan DI で adapter 配線
- [x] Port-Adapter で外部依存閉じ込め
- [x] training job と API job の分離
- [x] `make test` 通過

## 実装済

- [x] FastAPI 入口 (`app/api/`)
- [x] lifespan DI 配線 (`app/composition_root.py` / container)
- [x] Port (Protocol) / Adapter 分離
- [x] training job 分離 (`pipeline/training_job/`)
- [x] container による adapter 配線

## 未実装

無し (Phase 2 はクローズ済)。

## 次 Phase

`3/study-hybrid-search-local/` — ローカル不動産ハイブリッド検索の学習フェーズ。
