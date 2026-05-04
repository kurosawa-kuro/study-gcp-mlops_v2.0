"""Seed California Housing into PostgreSQL."""

from pathlib import Path

import pandas as pd
from sklearn.datasets import fetch_california_housing

from app.config import Settings
from common.logging import get_logger
from ml.container import build_container

logger = get_logger(__name__)
DATASET_DIR = Path("ml/data/datasets")
DATASET_PATH = DATASET_DIR / "california_housing.csv"


def _load_or_create_dataset() -> pd.DataFrame:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    if DATASET_PATH.exists():
        return pd.read_csv(DATASET_PATH)
    data = fetch_california_housing(as_frame=True)
    df = data.frame  # type: ignore[union-attr]
    df = df.rename(columns={"MedHouseVal": "Price"})
    df.to_csv(DATASET_PATH, index=False)
    return df


def main() -> None:
    settings = Settings()
    container = build_container(settings)
    df = _load_or_create_dataset()
    train_df = df.sample(frac=0.8, random_state=42)
    test_df = df.drop(train_df.index)
    container.dataset.write("train", train_df)
    container.dataset.write("test", test_df)
    logger.info("Seed complete: train=%d test=%d", len(train_df), len(test_df))


if __name__ == "__main__":
    main()
