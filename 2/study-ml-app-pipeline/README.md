# study-ml-app-pipeline

Phase 2 は、Phase 1 の California Housing 回帰を土台に、**App / Pipeline / Port-Adapter** を導入するフェーズ。

不変の中核:

- California Housing
- LightGBM 回帰
- preprocess / evaluation / artifact 出力

変えるのは ML コアではなく、呼び出し方と依存方向。

## Phase 2 の主役

| 技術 | 役割 |
|---|---|
| FastAPI | API 入口 |
| lifespan DI | 依存配線 |
| Port-Adapter | 依存方向整理 |
| job 分離 | API と学習処理の分離 |
| container | adapter 配線 |

## この Phase でやらないこと

- Meilisearch / multilingual-e5 / Redis
- 不動産検索ドメイン
- Cloud Run / BigQuery / GCS / Pub/Sub
- Terraform / WIF / Secret Manager
- Vertex AI / BQML / Dataflow / RAG / GKE

## ドキュメント

- [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md): Phase 2 の決定的仕様
- [docs/01_仕様と設計.md](docs/01_仕様と設計.md): 実装配置
- [CLAUDE.md](CLAUDE.md): 作業ガイド
