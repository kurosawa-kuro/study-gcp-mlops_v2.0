"""Common fixtures."""

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text


@pytest.fixture()
def sample_df():
    rng = np.random.RandomState(0)
    n = 100
    return pd.DataFrame(
        {
            "MedInc": rng.uniform(1, 10, n),
            "HouseAge": rng.uniform(1, 50, n),
            "AveRooms": rng.uniform(2, 10, n),
            "AveBedrms": rng.uniform(0.5, 3, n),
            "Population": rng.uniform(100, 5000, n),
            "AveOccup": rng.uniform(1, 6, n),
            "Latitude": rng.uniform(32, 42, n),
            "Longitude": rng.uniform(-124, -114, n),
            "Price": rng.uniform(0.5, 5, n),
        }
    )


@pytest.fixture(scope="session")
def postgres_url():
    testcontainers = pytest.importorskip(
        "testcontainers.postgres",
        reason="testcontainers-postgres is required for DB-backed tests",
    )
    with testcontainers.PostgresContainer("postgres:16") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2", "postgresql+psycopg")
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        yield url


@pytest.fixture()
def sample_db(postgres_url, sample_df):
    engine = create_engine(postgres_url, future=True)
    train_df = sample_df.iloc[:80]
    test_df = sample_df.iloc[80:]
    with engine.begin() as conn:
        train_df.to_sql("training_data", conn, if_exists="replace", index=False)
        test_df.to_sql("test_data", conn, if_exists="replace", index=False)
        conn.execute(text("DROP TABLE IF EXISTS prediction_runs"))
    engine.dispose()
    return postgres_url
