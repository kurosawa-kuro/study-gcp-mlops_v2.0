# TASKS.md (Phase 1)

`docs/02_移行ロードマップ.md` (長期 backlog/index) の current-sprint 抜粋。Claude Code の新セッションで「今 Phase で何をやり、何をやらないか」を最初に確認する単一エントリポイント。

## 現在の目的

Phase 1 = California Housing 回帰で **データ投入 → 前処理 → 特徴量 → 学習 → 評価 → 成果物保存** を一通り学ぶ ML 基礎フェーズ。**完了済 (アーカイブ運用)**。

## 今回の作業対象

新規作業は基本無し。以下の保守目的のみ:

- `02_移行ロードマップ.md` の不変ルールに反しない範囲のドキュメント / コードの軽微修正
- `make test` で回帰しない範囲の Python / 依存パッケージの追従

## 今回はやらない

- FastAPI / lifespan DI / Port-Adapter / job 分離 (Phase 2 へ)
- Meilisearch / multilingual-e5 / Redis / LightGBM LambdaRank / 不動産検索ドメイン (Phase 3 へ)
- Cloud Run / BigQuery / GCS / Pub/Sub / Terraform / WIF / Secret Manager (Phase 4 へ)
- Vertex AI / BQML / Dataflow / Explainable AI / GKE (Phase 5 以降へ)

## 完了条件 (達成済)

- [x] `make build` / `make seed` / `make train` / `make test` が通る
- [x] `ml/registry/artifacts/{run_id}/model.lgb` + `metrics.json` 生成
- [x] `ml/registry/artifacts/latest` シンボリックリンク更新

## 実装済

- [x] PostgreSQL 接続 (Repository pattern, `DATA_SOURCE` env で切替)
- [x] California Housing データ投入 (`pipeline/data_job/main.py`)
- [x] 前処理 / 特徴量生成 (`ml/data/preprocess` / `feature_engineering`)
- [x] LightGBM 学習 (`ml/training`)
- [x] RMSE / R² 評価 (`ml/evaluation`, numpy 自前実装)
- [x] Run ID + シンボリックリンク (`ml/registry`)
- [x] testcontainers PostgreSQL 統合テスト
- [x] 構造化ロギング (`ml/common/logging/logger.py`)

## 未実装

無し (Phase 1 はクローズ済)。

## 次 Phase

`2/study-ml-app-pipeline/` — App + Pipeline + Port/Adapter 導入フェーズ。
