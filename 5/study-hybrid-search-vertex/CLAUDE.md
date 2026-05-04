# CLAUDE.md

Phase 5 (`study-hybrid-search-vertex`) の作業ガイド。正本は [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)。

## 最初に読むもの

1. [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)
2. [docs/01_仕様と設計.md](docs/01_仕様と設計.md)
3. [docs/03_実装カタログ.md](docs/03_実装カタログ.md)
4. [docs/04_運用.md](docs/04_運用.md)

## 不変ルール

- 題材は不動産ハイブリッド検索
- 検索中核は `LightGBM + multilingual-e5 + Meilisearch + Vertex Vector Search + RRF`(Phase 4 の BigQuery `VECTOR_SEARCH` 経路は本 Phase で Vertex Vector Search に置換 — 2026-05-01 改定。詳細 `docs/02_移行ロードマップ.md §0`)
- Phase 5 は Vertex 標準 MLOps を学ぶフェーズ
- Phase 6 の PMLE 追加技術や Phase 7 の GKE serving 差分は持ち込まない

## Phase 5 の対象

- Vertex AI Pipelines
- Vertex AI Endpoints
- **Vertex Vector Search** (ME5 ベクトル検索の本番 serving index + ANN 検索。embedding 生成履歴・メタデータの正本は BigQuery 側に置き続ける)
- Model Registry
- **Vertex AI Feature Store (Feature Group / Feature View / Feature Online Store)(必須)** — training-serving skew 防止のため Phase 5 で必ず導入する。Phase 4 の BQ feature table / view を入力源とし、training (`pipeline/`) と serving (`app/`) の双方が同一 feature を読む
- Model Monitoring

## 実装ルール

- 検索コアは維持し、MLOps の責務だけを Vertex 側へ移す
- Feature parity は崩さない
- Terraform を正とする
- まず差分修正を優先し、E2E / CI/CD 検証は後段へ回す
