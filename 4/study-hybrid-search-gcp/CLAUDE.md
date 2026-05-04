# CLAUDE.md

Phase 4 (`study-hybrid-search-gcp`) の作業ガイド。正本は [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)。

## 最初に読むもの

1. [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)
2. [docs/01_仕様と設計.md](docs/01_仕様と設計.md)
3. [docs/03_実装カタログ.md](docs/03_実装カタログ.md)
4. [docs/04_運用.md](docs/04_運用.md)

## 不変ルール

- 題材は不動産ハイブリッド検索
- 検索中核は `LightGBM + multilingual-e5 + Meilisearch + BigQuery VECTOR_SEARCH + RRF`
- Phase 4 は GCP serverless 基盤を学ぶフェーズ
- Secret Manager は必須習得要素
- Vertex 以降の責務は持ち込まない

## Phase 4 の対象

- Cloud Run
- BigQuery
- GCS
- Pub/Sub
- Terraform
- Workload Identity Federation
- Secret Manager

## 実装ルール

- 検索コアは維持し、実行基盤だけを GCP へ移す
- Feature parity は崩さない
- Terraform を正とする
- まず差分修正を優先し、E2E / CI/CD 検証は後段へ回す
