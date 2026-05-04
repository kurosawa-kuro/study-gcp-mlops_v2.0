"""Evaluation tests."""

from pathlib import Path

import numpy as np

from ml.evaluation.metrics import evaluate, r2_score, rmse, save_metrics


def test_rmse_perfect():
    y = np.array([1.0, 2.0, 3.0])
    assert rmse(y, y) == 0.0


def test_r2_perfect():
    y = np.array([1.0, 2.0, 3.0])
    assert r2_score(y, y) == 1.0


def test_evaluate_returns_keys():
    y_true = np.array([1.0, 2.0, 3.0])
    y_pred = np.array([1.1, 2.1, 2.9])
    result = evaluate(y_true, y_pred)
    assert "rmse" in result
    assert "r2" in result


def test_save_metrics_creates_file(tmp_path):
    path = str(tmp_path / "metrics.json")
    save_metrics({"rmse": 0.5, "r2": 0.8}, path)
    assert Path(path).exists()
