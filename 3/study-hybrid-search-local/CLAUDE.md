# CLAUDE.md

Phase 3 (`study-hybrid-search-local`) の作業ガイド。正本は [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)。

## 最初に読むもの

1. [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)
2. [docs/01_仕様と設計.md](docs/01_仕様と設計.md)
3. [docs/03_実装カタログ.md](docs/03_実装カタログ.md)
4. [docs/04_運用.md](docs/04_運用.md)

## 不変ルール

- 題材は不動産ハイブリッド検索
- Local 中核は `Meilisearch + multilingual-e5 + Redis + LightGBM LambdaRank`
- `Meilisearch` は `Elasticsearch` より導入しやすいため採用
- Phase 3 はローカル実行基盤を学ぶフェーズ
- Cloud / Vertex / GKE 系の責務は持ち込まない

## Phase 3 の対象

- Meilisearch
- multilingual-e5
- Redis
- LightGBM LambdaRank
- PostgreSQL
- Docker Compose

## 実装ルール

- ローカルで検索・学習・評価が一巡する構成を維持する
- Cloud 前提の責務は入れない
- まず差分修正を優先し、E2E / CI/CD 検証は後段へ回す
