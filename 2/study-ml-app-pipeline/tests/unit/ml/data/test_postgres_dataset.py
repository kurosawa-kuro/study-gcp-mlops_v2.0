"""PostgreSQL dataset adapter tests."""

from ml.data.postgres_dataset import PostgresDatasetAdapter


def test_load_train(sample_db):
    adapter = PostgresDatasetAdapter(sample_db)
    df = adapter.load("train")
    assert len(df) == 80
    assert "Price" in df.columns


def test_load_test(sample_db):
    adapter = PostgresDatasetAdapter(sample_db)
    df = adapter.load("test")
    assert len(df) == 20
    assert "Price" in df.columns
