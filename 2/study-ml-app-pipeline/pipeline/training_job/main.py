"""Train job entrypoint."""

from app.config import Settings
from common.logging import get_logger
from common.run_id import generate_run_id
from ml.container import build_container
from ml.data.feature_engineering import engineer_features
from ml.data.preprocess import preprocess
from ml.training.trainer import train

logger = get_logger(__name__)


def main() -> None:
    settings = Settings()
    container = build_container(settings)
    run_id = generate_run_id()

    train_df = container.dataset.load("train")
    test_df = container.dataset.load("test")

    train_df = engineer_features(preprocess(train_df))
    test_df = engineer_features(preprocess(test_df))

    booster, metrics = train(train_df, test_df)
    payload = dict(metrics)
    payload["run_id"] = run_id
    container.model_store.save(run_id, booster, payload)
    logger.info("Training completed: run_id=%s", run_id)


if __name__ == "__main__":
    main()
