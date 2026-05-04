"""Predictor adapter backed by ModelStore."""

from ml.serving.inference import predict_price
from ml.registry.port import ModelStore
from ml.serving.port import Predictor


class ModelStorePredictor(Predictor):
    def __init__(self, model_store: ModelStore) -> None:
        self.model_store = model_store
        self._booster = None

    def warmup(self) -> None:
        self._booster = self.model_store.load("latest")

    def predict(self, values: dict) -> float:
        if self._booster is None:
            self.warmup()
        return predict_price(self._booster, values)
