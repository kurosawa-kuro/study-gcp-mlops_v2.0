"""Model evaluation helpers."""

import json
from pathlib import Path

import numpy as np

from common.logging import get_logger

logger = get_logger(__name__)


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot == 0.0:
        return 0.0 if ss_res == 0.0 else float("nan")
    return 1 - ss_res / ss_tot


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "rmse": round(rmse(y_true, y_pred), 4),
        "r2": round(r2_score(y_true, y_pred), 4),
    }


def save_metrics(metrics: dict, path: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    logger.info("Metrics saved to %s", out)
