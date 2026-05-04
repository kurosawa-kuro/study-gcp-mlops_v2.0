"""Smoke test for ``LightGBMRankerTrainer`` (Phase C-1).

Builds a tiny synthetic dataset + verifies the adapter satisfies the
``RankerTrainer`` Port contract end-to-end. Marked slow because it
shells out to the real LightGBM C extension.
"""

from __future__ import annotations

import pytest

from ml.training.adapters import LightGBMRankerTrainer
from ml.training.ports import RankerTrainer

pytest.importorskip("lightgbm")


def test_lightgbm_trainer_satisfies_ranker_trainer_protocol() -> None:
    trainer: RankerTrainer = LightGBMRankerTrainer(num_iterations=10, early_stopping_rounds=5)

    feature_names = ["f0", "f1", "f2"]
    train_features = [
        [1.0, 0.0, 0.0],
        [0.5, 0.5, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    train_labels = [3.0, 2.0, 1.0, 0.0]
    train_groups = [4]
    test_features = train_features
    test_labels = train_labels
    test_groups = train_groups
    params = {
        "objective": "lambdarank",
        "metric": ["ndcg"],
        "ndcg_eval_at": [3],
        "num_leaves": 7,
        "learning_rate": 0.1,
        "feature_fraction": 1.0,
        "bagging_fraction": 1.0,
        "bagging_freq": 0,
        "min_data_in_leaf": 1,
        "lambdarank_truncation_level": 3,
        "verbosity": -1,
    }

    result = trainer.train(
        train_features=train_features,
        train_labels=train_labels,
        train_groups=train_groups,
        test_features=test_features,
        test_labels=test_labels,
        test_groups=test_groups,
        feature_names=feature_names,
        params=params,
    )

    scores = result.model.predict(train_features)
    assert len(scores) == len(train_features)
    # Predict-with-explain should fit the same shape
    pred_scores, attrs = result.model.predict_with_explain(train_features, feature_names)
    assert len(pred_scores) == len(train_features)
    assert len(attrs) == len(train_features)
    for row in attrs:
        assert "_baseline" in row
        for name in feature_names:
            assert name in row
