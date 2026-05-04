# Pipeline Orchestration

このドキュメントはハイブリッド検索 MLOps プラットフォームのジョブ連鎖を記述する。

## ジョブ DAG

```
Dataform (definitions/)  -->  pipeline/data_job   -->  pipeline/training_job  -->  pipeline/evaluation_job
                                                                                    |
                                                                                    v
                                                                        pipeline/batch_serving_job
```

1. **data_job**: `properties_cleaned` → 埋め込みベクトル再計算 → BigQuery へ upsert (`property_embeddings`).
2. **training_job**: `property_features_daily` から訓練行を取得し LightGBM LambdaRank を学習、Vertex Model へ登録。
3. **evaluation_job**: 訓練済みランカーのゲーティング（NDCG / Recall / MAP の閾値判定、skew 検査）。
4. **batch_serving_job**: 既知クエリに対するバッチ予測（オンライン serving 負荷を事前に逃がす）。

## Vertex AI Pipelines

- 各ジョブの `main.py` が `@dsl.pipeline` を公開する。
- `pipeline/workflow/compile.py` が KFP コンパイラで `.compiled/pipelines/*.yaml` を生成し、Vertex の `PipelineJob` として投入する。
- 起動は `pipeline/workflow/trigger.py` (Cloud Functions) が Pub/Sub イベントに応じて行う。

## スケジュール

- data_job: 日次（Dataform 完了後）
- training_job: 週次 + `training_policy` による on-demand
- evaluation_job: training_job 完了時にチェイン
- batch_serving_job: 日次（利用頻度の高いクエリセット向け）

## 参照

- [docs/runbook/05_運用.md](../../docs/runbook/05_運用.md)
- [docs/architecture/01_仕様と設計.md](../../docs/architecture/01_仕様と設計.md)
