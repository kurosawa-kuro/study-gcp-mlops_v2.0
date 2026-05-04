# study-hybrid-search-vertex

Phase 5 は、Phase 4 の不動産ハイブリッド検索を維持したまま、**Vertex 標準 MLOps** を実コードへ統合するフェーズ。

不変の検索中核:

- `Meilisearch`
- `Vertex Vector Search` (Phase 4 の `BigQuery VECTOR_SEARCH` を本 Phase で置換 — 2026-05-01 改定)
- `multilingual-e5`
- `RRF`
- `LightGBM LambdaRank`

変えるのは MLOps の実行責務、および ME5 ベクトルの格納先 (BQ → Vertex Vector Search)。

## Phase 5 の主役

| 技術 | 役割 |
|---|---|
| Vertex AI Pipelines | 学習・埋め込み DAG |
| Vertex AI Endpoints | encoder / reranker 推論 |
| **Vertex Vector Search** | **ME5 ベクトル検索の本番 serving index (ANN、semantic 経路)。embedding 生成履歴・メタデータの正本は BigQuery 側に残す** |
| Model Registry | モデル版管理 |
| **Vertex AI Feature Store (Feature Group / Feature View / Feature Online Store)(必須)** | **Phase 4 の BQ feature table / view を入力源に、training と serving で同一 feature を取り出す経路を確立(training-serving skew 防止)** |
| Model Monitoring | drift 監視 |

## この Phase でやらないこと

- BQML
- Dataflow
- Monitoring SLO
- Explainable AI
- GKE / KServe

加えて親リポ `README.md` §1 / `docs/02_移行ロードマップ.md §1.4` に列挙された全 Phase 共通禁止技術 (Agent Builder / Vizier / Model Garden / Gemini RAG / W&B / Looker Studio / Doppler) は本 Phase でも扱わない。Vertex Vector Search は 2026-05-01 改定で禁止リストから外し、本 Phase の semantic 検索の本番 serving index に採用した(embedding 生成履歴・メタデータの正本は BigQuery 側に残す)。

## ドキュメント

- [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md): Phase 5 の決定的仕様
- [docs/01_仕様と設計.md](docs/01_仕様と設計.md): 実装配置
- [docs/03_実装カタログ.md](docs/03_実装カタログ.md): 実装棚卸し
- [docs/04_運用.md](docs/04_運用.md): 運用手順
- [CLAUDE.md](CLAUDE.md): 作業ガイド
