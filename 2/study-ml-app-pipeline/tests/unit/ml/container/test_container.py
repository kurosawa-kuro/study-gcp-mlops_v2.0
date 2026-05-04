"""Container wiring smoke test."""

from app.config import Settings
from ml.container import build_container


def test_build_container(tmp_path):
    settings = Settings(
        model_dir=str(tmp_path / "artifacts"),
        postgres_host="localhost",
    )
    container = build_container(settings)
    assert container.dataset is not None
    assert container.model_store is not None
    assert container.predictor is not None
