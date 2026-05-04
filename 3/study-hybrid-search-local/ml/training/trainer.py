"""Phase 3 — LightGBM LambdaRank trainer (minimal, local-only).

Phase 7 trainer から GCS / Vertex Experiments / RankerTrainingRepository (BigQuery)
依存を全削除し、ローカル PostgreSQL `ranking_log` を直接読む or 合成データに
fallback する形に書き直した版。

二段構成:
- :func:`train` — pure: train/test DataFrame を受け取り LightGBM Booster + metrics 返す
- :func:`run` — orchestration: synthetic / Postgres から学習データを引き、train + write artifacts

Phase 4 で BQ I/O / Cloud Run Jobs に差し替える際、Phase 7 trainer の構造に近づける。
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.common import generate_run_id, get_logger
from ml.data.feature_engineering import (
    FEATURE_COLS_RANKER,
    RANKER_GROUP_COL,
    RANKER_LABEL_COL,
)
from ml.evaluation.metrics import evaluate
from ml.registry.artifact_store import LocalArtifactStore
from ml.training.model_builder import split_by_request_id, synthetic_ranking_frames

logger = get_logger("ml.training.trainer")

PRIMARY_METRIC: str = "ndcg@10"


@dataclass(frozen=True)
class TrainingResult:
    run_id: str
    booster: lgb.Booster
    metrics: dict[str, float]
    num_train_rows: int
    num_eval_rows: int
    feature_importance: dict[str, float]


@dataclass(frozen=True)
class HyperParams:
    objective: str = "lambdarank"
    metric: str = "ndcg"
    num_leaves: int = 31
    learning_rate: float = 0.05
    num_boost_round: int = 200
    early_stopping_rounds: int = 30


def train(
    *,
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    hp: HyperParams | None = None,
) -> tuple[lgb.Booster, dict[str, float], dict[str, float]]:
    """LightGBM LambdaRank fit。

    Returns: (booster, metrics, feature_importance)
    """
    hp = hp or HyperParams()

    if train_df.empty:
        raise ValueError("train_df is empty — cannot train LambdaRank")

    train_X = train_df[FEATURE_COLS_RANKER].to_numpy(dtype=np.float64)
    train_y = train_df[RANKER_LABEL_COL].to_numpy(dtype=np.int32)
    train_groups = train_df.groupby(RANKER_GROUP_COL, sort=False).size().to_numpy()

    train_set = lgb.Dataset(train_X, label=train_y, group=train_groups)

    valid_sets = [train_set]
    valid_names = ["train"]
    if not eval_df.empty:
        eval_X = eval_df[FEATURE_COLS_RANKER].to_numpy(dtype=np.float64)
        eval_y = eval_df[RANKER_LABEL_COL].to_numpy(dtype=np.int32)
        eval_groups = eval_df.groupby(RANKER_GROUP_COL, sort=False).size().to_numpy()
        eval_set = lgb.Dataset(eval_X, label=eval_y, group=eval_groups, reference=train_set)
        valid_sets.append(eval_set)
        valid_names.append("eval")

    params: dict[str, object] = {
        "objective": hp.objective,
        "metric": hp.metric,
        "num_leaves": hp.num_leaves,
        "learning_rate": hp.learning_rate,
        "verbose": -1,
        "label_gain": [0, 1, 3, 7],  # 0..3 のラベルに対する LambdaRank gain
    }
    booster = lgb.train(
        params=params,
        train_set=train_set,
        num_boost_round=hp.num_boost_round,
        valid_sets=valid_sets,
        valid_names=valid_names,
        callbacks=[
            lgb.early_stopping(hp.early_stopping_rounds, verbose=False),
            lgb.log_evaluation(period=0),
        ],
    )

    if not eval_df.empty:
        eval_X = eval_df[FEATURE_COLS_RANKER].to_numpy(dtype=np.float64)
        eval_y = eval_df[RANKER_LABEL_COL].to_numpy(dtype=np.int32)
        eval_preds = booster.predict(eval_X)
        # evaluate は per-query group の集計を期待する。groups は group sizes。
        eval_groups = eval_df.groupby(RANKER_GROUP_COL, sort=False).size().to_numpy()
        metrics = evaluate(
            labels=eval_y,
            scores=np.asarray(eval_preds),
            groups=eval_groups,
            k_ndcg=10,
            k_recall=20,
        )
    else:
        metrics = {}

    importance = booster.feature_importance(importance_type="gain")
    feature_importance = {
        col: float(val) for col, val in zip(FEATURE_COLS_RANKER, importance, strict=True)
    }

    return booster, metrics, feature_importance


def write_artifacts(
    *,
    run_id: str,
    booster: lgb.Booster,
    metrics: dict[str, float],
    feature_importance: dict[str, float],
    artifacts_root: Path,
    hp: HyperParams,
) -> Path:
    """成果物 3 種をローカルに書き出し、`latest` シンボリックリンクを更新する。"""
    store = LocalArtifactStore(root=artifacts_root)
    run_dir = store.run_dir(run_id)

    model_path = run_dir / "model.lgb"
    booster.save_model(str(model_path))

    metrics_path = run_dir / "metrics.json"
    metrics_payload = {
        "run_id": run_id,
        "trained_at": datetime.now(UTC).isoformat(),
        "hyperparameters": {
            "objective": hp.objective,
            "metric": hp.metric,
            "num_leaves": hp.num_leaves,
            "learning_rate": hp.learning_rate,
            "num_boost_round": hp.num_boost_round,
            "early_stopping_rounds": hp.early_stopping_rounds,
        },
        "metrics": {k: float(v) for k, v in metrics.items()},
    }
    metrics_path.write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2))

    fi_path = run_dir / "feature_importance.csv"
    with fi_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["feature", "importance"])
        for col, val in feature_importance.items():
            writer.writerow([col, float(val)])

    store.update_latest(run_id)
    logger.info("write_artifacts: run_id=%s model=%s", run_id, model_path)
    return run_dir


def run(
    *,
    artifacts_root: Path,
    df: pd.DataFrame | None = None,
    hp: HyperParams | None = None,
    run_id: str | None = None,
) -> TrainingResult:
    """学習 1 回分の orchestration。

    ``df`` が渡されない / 空なら ``synthetic_ranking_frames`` で合成データに fallback。
    Phase 4 では BigQuery / Postgres ranking_log loader を渡す想定。
    """
    hp = hp or HyperParams()
    run_id = run_id or generate_run_id()

    if df is None or df.empty:
        train_df, eval_df = synthetic_ranking_frames(seed=42)
        logger.info("synthetic ranking frames: train=%d eval=%d", len(train_df), len(eval_df))
    else:
        train_df, eval_df = split_by_request_id(df, train_ratio=0.8)
        logger.info("split_by_request_id: train=%d eval=%d", len(train_df), len(eval_df))

    booster, metrics, feature_importance = train(train_df=train_df, eval_df=eval_df, hp=hp)

    write_artifacts(
        run_id=run_id,
        booster=booster,
        metrics=metrics,
        feature_importance=feature_importance,
        artifacts_root=artifacts_root,
        hp=hp,
    )

    return TrainingResult(
        run_id=run_id,
        booster=booster,
        metrics=metrics,
        num_train_rows=len(train_df),
        num_eval_rows=len(eval_df),
        feature_importance=feature_importance,
    )
