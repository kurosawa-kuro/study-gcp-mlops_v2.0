"""LightGBM-backed ``RankerTrainer`` / ``RankerModel`` adapter.

Isolates the ``lightgbm`` import to this module so ``ml/training/trainer.py``
(orchestration) can stay SDK-free once the Phase C-1 refactor lands.
The concrete ``train()`` body mirrors the existing
``ml/training/trainer.py::train`` helper.
"""

from __future__ import annotations

from typing import Any

import lightgbm as lgb
import numpy as np

from ml.training.ports.ranker_model import RankerModel
from ml.training.ports.ranker_trainer import RankerTrainer, TrainingResult


class LightGBMModel(RankerModel):
    """Wraps a fitted ``lgb.Booster``.

    ``predict_with_explain`` calls ``Booster.predict`` twice:
    once for raw scores and once with ``pred_contrib=True`` for SHAP
    attributions (last column is the bias / baseline; renamed to
    ``_baseline`` in the returned dict for downstream parity with
    ``app/services/adapters/kserve_reranker.py`` payloads).
    """

    def __init__(self, booster: lgb.Booster) -> None:
        self._booster = booster

    def predict(self, features: list[list[float]]) -> list[float]:
        if not features:
            return []
        arr = np.asarray(features, dtype=float)
        return [float(x) for x in self._booster.predict(arr)]

    def predict_with_explain(
        self,
        features: list[list[float]],
        feature_names: list[str],
    ) -> tuple[list[float], list[dict[str, float]]]:
        if not features:
            return [], []
        arr = np.asarray(features, dtype=float)
        scores = [float(x) for x in self._booster.predict(arr)]
        contributions = self._booster.predict(arr, pred_contrib=True)
        attributions: list[dict[str, float]] = []
        for row in contributions:
            entry: dict[str, float] = {
                name: float(row[idx]) for idx, name in enumerate(feature_names)
            }
            entry["_baseline"] = float(row[-1])
            attributions.append(entry)
        return scores, attributions

    def save(self, path: str) -> None:
        self._booster.save_model(path)


class LightGBMRankerTrainer(RankerTrainer):
    """LambdaRank trainer — wraps ``lgb.train`` with the Phase 4 hyperparams."""

    def __init__(
        self,
        *,
        num_iterations: int = 1000,
        early_stopping_rounds: int = 30,
        log_period: int = 20,
    ) -> None:
        self._num_iterations = num_iterations
        self._early_stopping_rounds = early_stopping_rounds
        self._log_period = log_period

    def train(
        self,
        *,
        train_features: list[list[float]],
        train_labels: list[float],
        train_groups: list[int],
        test_features: list[list[float]],
        test_labels: list[float],
        test_groups: list[int],
        feature_names: list[str],
        params: dict[str, object],
    ) -> TrainingResult:
        x_train = np.asarray(train_features, dtype=float)
        y_train = np.asarray(train_labels, dtype=float)
        g_train = np.asarray(train_groups, dtype=int)
        x_test = np.asarray(test_features, dtype=float)
        y_test = np.asarray(test_labels, dtype=float)
        g_test = np.asarray(test_groups, dtype=int)

        train_set = lgb.Dataset(
            x_train,
            label=y_train,
            group=g_train,
            feature_name=feature_names,
        )
        valid_set = lgb.Dataset(
            x_test,
            label=y_test,
            group=g_test,
            reference=train_set,
            feature_name=feature_names,
        )

        booster = lgb.train(
            params,
            train_set,
            num_boost_round=self._num_iterations,
            valid_sets=[valid_set],
            callbacks=[
                lgb.early_stopping(stopping_rounds=self._early_stopping_rounds),
                lgb.log_evaluation(period=self._log_period),
            ],
        )

        # Caller computes evaluation metrics; the trainer only reports the
        # best iteration so far.
        metrics: dict[str, Any] = {
            "best_iteration": int(booster.best_iteration or self._num_iterations),
        }

        hyperparams = dict(params)
        hyperparams["num_iterations"] = self._num_iterations
        hyperparams["early_stopping_rounds"] = self._early_stopping_rounds

        return TrainingResult(
            model=LightGBMModel(booster),
            metrics=metrics,
            hyperparams=hyperparams,
        )
