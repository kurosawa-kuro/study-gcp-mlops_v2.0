"""PostgreSQL dataset adapter."""

from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ml.data.port import DatasetReader


class PostgresDatasetAdapter(DatasetReader):
    _ALLOWED_TABLES = {"training_data", "test_data"}

    def __init__(self, dsn: str) -> None:
        self.engine: Engine = create_engine(dsn, future=True)

    def _ensure_tables(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS prediction_runs (
                        run_id TEXT NOT NULL,
                        row_id BIGINT NOT NULL,
                        price DOUBLE PRECISION NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (run_id, row_id)
                    )
                    """
                )
            )

    def load(self, split: str) -> pd.DataFrame:
        table = "training_data" if split == "train" else "test_data"
        if table not in self._ALLOWED_TABLES:
            raise ValueError(f"Invalid split: {split}")
        with self.engine.connect() as conn:
            return pd.read_sql(text(f"SELECT * FROM {table}"), conn)

    def write(self, split: str, frame: pd.DataFrame) -> None:
        table = "training_data" if split == "train" else "test_data"
        if table not in self._ALLOWED_TABLES:
            raise ValueError(f"Invalid split: {split}")
        with self.engine.begin() as conn:
            frame.to_sql(table, conn, if_exists="replace", index=False)

    def write_predictions(self, run_id: str, frame: pd.DataFrame) -> None:
        self._ensure_tables()
        payload = frame.copy().reset_index(drop=True)
        payload["run_id"] = run_id
        payload["row_id"] = payload.index.astype("int64")
        payload["created_at"] = datetime.now()
        with self.engine.begin() as conn:
            payload[["run_id", "row_id", "Price", "created_at"]].rename(
                columns={"Price": "price"}
            ).to_sql(
                "prediction_runs",
                conn,
                if_exists="append",
                index=False,
            )
