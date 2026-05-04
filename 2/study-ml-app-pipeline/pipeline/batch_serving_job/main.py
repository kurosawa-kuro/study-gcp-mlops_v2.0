"""Batch prediction job entrypoint."""

from app.config import Settings
from common.logging import get_logger
from common.run_id import generate_run_id
from ml.container import build_container
from ml.data.feature_engineering import engineer_features
from ml.data.preprocess import preprocess
from ml.training.trainer import predict

logger = get_logger(__name__)


def main() -> None:
    settings = Settings()
    container = build_container(settings)
    source_df = container.dataset.load("test")
    frame = engineer_features(preprocess(source_df))
    booster = container.model_store.load("latest")
    predictions = predict(booster, frame)
    container.dataset.write_predictions(generate_run_id(), predictions.to_frame())
    logger.info("Batch prediction completed: %d rows", len(predictions))


if __name__ == "__main__":
    main()
