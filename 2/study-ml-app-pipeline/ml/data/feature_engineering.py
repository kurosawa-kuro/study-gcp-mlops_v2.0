"""Feature engineering logic."""

import pandas as pd

from common.logging import get_logger

logger = get_logger(__name__)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["BedroomRatio"] = df["AveBedrms"] / df["AveRooms"]
    df["RoomsPerPerson"] = df["AveRooms"] / df["AveOccup"]
    logger.info("Engineered 2 features: BedroomRatio, RoomsPerPerson")
    return df


def engineer_features_input(values: dict) -> dict:
    out = dict(values)
    out["BedroomRatio"] = out["AveBedrms"] / out["AveRooms"]
    out["RoomsPerPerson"] = out["AveRooms"] / out["AveOccup"]
    return out
