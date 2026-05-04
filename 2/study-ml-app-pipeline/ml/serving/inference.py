"""Single-record prediction use-case."""

import numpy as np

from ml.data.feature_engineering import engineer_features_input
from ml.data.preprocess import preprocess_input
from ml.data.schema import MODEL_COLS


def predict_price(booster, values: dict) -> float:
    transformed = preprocess_input(values)
    transformed = engineer_features_input(transformed)
    features = np.array([[transformed[col] for col in MODEL_COLS]])
    prediction = booster.predict(features)[0]
    return round(float(prediction), 4)
