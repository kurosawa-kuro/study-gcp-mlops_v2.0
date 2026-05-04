"""Training and prediction use-cases."""

from pathlib import Path

import lightgbm as lgb
import pandas as pd

from common.logging import get_logger
from ml.data.schema import MODEL_COLS, TARGET_COL
from ml.evaluation.metrics import evaluate, save_metrics

logger = get_logger(__name__)
NUM_BOOST_ROUND = 300


def build_training_params() -> dict:
    return {
        "objective": "regression",
        "metric": "rmse",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "verbosity": -1,
    }


def train(train_df: pd.DataFrame, test_df: pd.DataFrame) -> tuple[lgb.Booster, dict]:
    x_train = train_df[MODEL_COLS].values
    y_train = train_df[TARGET_COL].values
    x_test = test_df[MODEL_COLS].values
    y_test = test_df[TARGET_COL].values

    train_set = lgb.Dataset(x_train, label=y_train)
    valid_set = lgb.Dataset(x_test, label=y_test, reference=train_set)

    booster = lgb.train(
        build_training_params(),
        train_set,
        num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[valid_set],
        callbacks=[lgb.log_evaluation(period=50)],
    )

    y_pred = booster.predict(x_test)
    metrics = evaluate(y_test, y_pred)
    return booster, metrics


def persist_training_result(
    booster: lgb.Booster,
    metrics: dict,
    model_dir: str,
    run_id: str,
) -> dict:
    result = dict(metrics)
    result["run_id"] = run_id
    run_dir = Path(model_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(run_dir / "model.lgb"))
    save_metrics(result, str(run_dir / "metrics.json"))
    logger.info("Model saved to %s", run_dir / "model.lgb")
    return result


def predict(booster: lgb.Booster, frame: pd.DataFrame) -> pd.Series:
    values = booster.predict(frame[MODEL_COLS].values)
    return pd.Series(values, name=TARGET_COL)
