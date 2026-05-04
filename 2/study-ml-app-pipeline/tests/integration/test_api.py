"""API パッケージのテスト（推論エンドポイント）."""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def api_client(tmp_path, sample_df):
    """学習済みモデルを作成し、FastAPI TestClient を返す."""
    from ml.registry.filesystem_model_store import FilesystemModelStore
    from ml.data.feature_engineering import engineer_features
    from ml.data.preprocess import preprocess
    from ml.training.trainer import train

    model_dir = str(tmp_path / "ml" / "registry" / "artifacts")
    train_df = engineer_features(preprocess(sample_df.iloc[:80]))
    test_df = engineer_features(preprocess(sample_df.iloc[80:]))
    booster, metrics = train(train_df, test_df)
    FilesystemModelStore(model_dir).save("test_run", booster, metrics)

    os.environ["MODEL_DIR"] = model_dir

    with TestClient(app) as client:
        yield client

    os.environ.pop("MODEL_DIR", None)


class TestHealthEndpoint:
    def test_health(self, api_client):
        res = api_client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


class TestPredictEndpoint:
    def test_predict_returns_price(self, api_client):
        payload = {
            "MedInc": 8.3,
            "HouseAge": 41,
            "AveRooms": 6.9,
            "AveBedrms": 1.0,
            "Population": 322,
            "AveOccup": 2.5,
            "Latitude": 37.88,
            "Longitude": -122.23,
        }
        res = api_client.post("/predict", json=payload)
        assert res.status_code == 200
        body = res.json()
        assert "predicted_price" in body
        assert isinstance(body["predicted_price"], float)
