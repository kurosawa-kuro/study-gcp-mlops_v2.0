# CLAUDE.md

Phase 3 (`study-hybrid-search-local`) の作業ガイド。正本は [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)。

## 最初に読むもの

1. [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)
2. [docs/01_仕様と設計.md](docs/01_仕様と設計.md)
3. [docs/03_実装カタログ.md](docs/03_実装カタログ.md)
4. [docs/04_運用.md](docs/04_運用.md)

## 不変ルール

- 題材は不動産ハイブリッド検索 (Phase 3-7 共通)
- 中核 5 要素: `Meilisearch BM25 + multilingual-e5 + pgvector + RRF + LightGBM LambdaRank` (Phase 3 では pgvector、Phase 4 = BQ `VECTOR_SEARCH`、Phase 7 = Vertex Vector Search)
- `Meilisearch` は `Elasticsearch` より導入しやすいため採用
- Phase 3 はローカル実行基盤を学ぶフェーズ + Phase 4 への足し算起点
- Cloud / Vertex / GKE 系の責務は持ち込まない (Phase 4 / 5 / 6 / 7 の責務)
- 設計思想 (Port/Adapter / DI / FastAPI lifespan) は Phase 2 から継承して不変

## Phase 3 の対象

- Meilisearch (Docker)
- multilingual-e5 (sentence-transformers, in-process)
- pgvector (PostgreSQL extension, ANN)
- Redis (キャッシュ)
- LightGBM LambdaRank (in-process)
- PostgreSQL (`properties` / `embeddings` / `feature_mart_property_features_daily` / `ranking_log` / `feedback_events`)
- Docker Compose (postgres+pgvector / meilisearch / redis / search-api 4 service)

## 実装ルール

- ローカルで検索・学習・評価が一巡する構成 (`make build && make seed && make train && make serve` で `/search` 動作)
- Cloud 前提の責務は入れない (`scripts/ci/layers.py` で `google.cloud` / `kserve` / `kfp` import を AST 検出)
- Phase 7 と完全同型の Port を保ち、Phase 4 で adapter のみ差し替えで足し算可能な構造を維持
- まず差分修正を優先し、E2E / CI/CD 検証は user 環境で `make verify-pipeline` を回す
