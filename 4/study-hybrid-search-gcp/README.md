# study-hybrid-search-gcp

Phase 4 は、Phase 3 の不動産ハイブリッド検索を維持したまま、**GCP serverless 実行基盤** へ移すフェーズ。

不変の検索中核:

- `Meilisearch`
- `BigQuery VECTOR_SEARCH`
- `multilingual-e5`
- `RRF`
- `LightGBM LambdaRank`

変えるのは検索コアではなく、実行基盤と運用基盤。

## Phase 4 の主役

| 技術 | 役割 |
|---|---|
| Cloud Run | API / job 実行 |
| BigQuery | 検索・特徴量・ログ |
| GCS | モデル成果物保管 |
| Pub/Sub | 非同期イベント |
| Terraform | IaC |
| WIF | CI/CD 認証 |
| Secret Manager | Meili key 注入 |

## この Phase でやらないこと

- Vertex AI Pipelines / Endpoints / Model Registry / Feature Group / Monitoring
- BQML
- Dataflow
- Monitoring SLO
- Explainable AI
- GKE / KServe
- 親 [`README.md` §1 教材対象外](../../README.md) / [`docs/02_移行ロードマップ.md` §1.4](../../docs/tasks/02_移行ロードマップ.md) の禁止技術

## ドキュメント

- [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md): Phase 4 の決定的仕様
- [docs/01_仕様と設計.md](docs/01_仕様と設計.md): 実装配置
- [docs/03_実装カタログ.md](docs/03_実装カタログ.md): 実装棚卸し
- [docs/04_運用.md](docs/04_運用.md): 運用手順
- [CLAUDE.md](CLAUDE.md): 作業ガイド
