# CLAUDE.md

Phase 1 (`study-ml-foundations`) で作業する Claude Code 向けガイド。MLOps 教育用のカリフォルニア住宅価格予測 ML パイプライン (**Phase 1: ML 基礎**)。LightGBM + Docker Compose でローカル完結。

## 最初に読むもの

1. [docs/TASKS.md](docs/TASKS.md) — current sprint
2. [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md) — 決定的仕様 (権威 1 位)
3. [docs/01_仕様と設計.md](docs/01_仕様と設計.md) — 機能仕様 + 設計
4. [docs/04_運用.md](docs/04_運用.md) — 運用 / Scripts / Docker / Configuration / Testing 詳細

## Project Overview

Phase 1 は **ML コア (データ取得 → 前処理 → 特徴量エンジニアリング → 学習 → 評価 → 保存)** に集中する。API や設計パターンは扱わない。

## Architecture

```
PostgreSQL (docker-compose: postgres サービス / volume: postgres_data)
  → pipeline/data_job: Repository パターンでデータ取得
    → ml/data/preprocess: 前処理 (欠損値補完・外れ値キャップ・対数変換)
      → ml/data/feature_engineering: 特徴量エンジニアリング (BedroomRatio・RoomsPerPerson)
        → ml/training: LightGBM 学習
          → ml/evaluation: 精度評価 (RMSE, R²) + metrics.json 保存
            → ml/registry/artifacts/{run_id}/ に保存 + PostgreSQL に精度記録 + latest シンボリックリンク更新
```

**Key design decisions:**

- **Docker 前提** — seed / train は `docker compose` 経由で実行。DB も同じ network 上の `postgres` サービスを使用
- **パッケージ間の責務分離**: pipeline (データ取得+オーケストレーション) / ml/training (学習) / ml/evaluation (評価+metrics.json) / ml/data (前処理+特徴量) / ml/common (共通)
- **Repository pattern** — `PostgresRepository` (SQLAlchemy + psycopg)、`DATA_SOURCE` env var で切り替え
- **No scikit-learn for metrics** — RMSE, R² は numpy で自前実装 (`ml/evaluation/metrics/regression.py`)
- **メトリクス管理** — RMSE / R² を `ml/registry/artifacts/{run_id}/metrics.json` に保存
- **Run ID** — `YYYYMMDD_HHMMSS_{6桁UUID}` でモデルにバージョン付与。`ml/registry/artifacts/latest` シンボリックリンクで最新を参照
- **構造化ロギング** — `ml/common/logging/logger.py` の `get_logger()` で統一。全モジュール `logger.info()` を使用
- **エラーハンドリング** — `pipeline/training_job/main.py` でデータ取得・学習の各ステップを try-except で保護
- **Makefile → scripts/ に委譲** — `scripts/core.py` に共通設定を集約

## Source Layout

```
pipeline/             ジョブ entrypoint (データ取得 + 学習 + 評価)
├── data_job/main.py        sklearn → PostgreSQL 投入
├── training_job/main.py    LightGBM 学習
└── evaluation_job/main.py  評価単発
ml/                   ML コア
├── data/             loaders / preprocess / feature_engineering / datasets
├── training/         trainer / model_builder / experiments
├── evaluation/       metrics / validators / comparators / report
├── registry/         model_registry / metadata_store / artifact_store
└── common/           config / logging / utils (schema / run_id)
tests/
├── conftest.py       共通フィクスチャ (sample_df / postgres_url / sample_db)
├── unit/ml/          trainer / evaluation / preprocess テスト
└── integration/      test_pipeline (testcontainers PostgreSQL)
infra/run/jobs/trainer/Dockerfile   seed / trainer イメージ
```

## Commands (要点)

詳細は [docs/04_運用.md](docs/04_運用.md) (Scripts / Docker サービス / Configuration / Dependencies / Testing)。

```bash
make build          # Docker イメージビルド
make seed           # sklearn データを PostgreSQL に投入 (Docker)
make train          # LightGBM 学習 → ml/registry/artifacts/{run_id}/ に保存 (Docker)
make test           # pytest 全テスト実行 (ローカル)
make run-all        # build → seed → train → test (monitor 付き)
make down           # Docker Compose 停止
make clean          # Docker 停止 + 生成ファイル削除
```

推論 API / `serve` は Phase 2 (`2/study-ml-app-pipeline/`) に移管済み。

## 不変ルール

- 題材は California Housing 回帰
- 学習器は LightGBM 回帰
- 評価は RMSE / R²
- 成果物は `run_id` / `model.lgb` / `metrics.json` を残す
- API や設計パターンは持ち込まない (Phase 2 以降)

## 権威順位

`docs/02_移行ロードマップ.md > docs/TASKS.md > docs/01_仕様と設計.md > README.md > CLAUDE.md`
