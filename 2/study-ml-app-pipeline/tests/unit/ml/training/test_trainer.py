"""Trainer tests."""

from pathlib import Path

from ml.data.feature_engineering import engineer_features
from ml.data.preprocess import preprocess
from ml.training.trainer import train


def test_train_returns_metrics_and_booster(sample_df, tmp_path):
    train_df = engineer_features(preprocess(sample_df.iloc[:80]))
    test_df = engineer_features(preprocess(sample_df.iloc[80:]))
    booster, metrics = train(train_df, test_df)

    assert "rmse" in metrics
    assert "r2" in metrics
    assert metrics["rmse"] > 0
    out = Path(tmp_path / "model.lgb")
    booster.save_model(str(out))
    assert out.exists()
