"""Pipeline integration tests."""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from pipeline.batch_serving_job.main import main as predict_main
from pipeline.training_job.main import main as train_main


def _apply_db_env(monkeypatch, postgres_url: str) -> None:
    parsed = make_url(postgres_url)
    monkeypatch.setenv("POSTGRES_HOST", parsed.host or "localhost")
    monkeypatch.setenv("POSTGRES_PORT", str(parsed.port or 5432))
    monkeypatch.setenv("POSTGRES_DB", parsed.database or "mlpipeline")
    monkeypatch.setenv("POSTGRES_USER", parsed.username or "admin")
    monkeypatch.setenv("POSTGRES_PASSWORD", parsed.password or "password")


def test_train_and_predict_jobs(sample_db, tmp_path, monkeypatch):
    _apply_db_env(monkeypatch, sample_db)
    model_dir = tmp_path / "ml" / "registry" / "artifacts"
    monkeypatch.setenv("MODEL_DIR", str(model_dir))
    monkeypatch.setenv("MODEL_PATH", str(model_dir / "latest" / "model.lgb"))

    train_main()

    latest = model_dir / "latest"
    assert latest.exists()
    assert (latest.resolve() / "model.lgb").exists()
    assert (latest.resolve() / "metrics.json").exists()

    predict_main()

    engine = create_engine(sample_db, future=True)
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM prediction_runs")).scalar_one()
    assert count > 0
    engine.dispose()
