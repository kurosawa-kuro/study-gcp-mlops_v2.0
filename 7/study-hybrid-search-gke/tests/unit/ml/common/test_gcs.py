from ml.registry.artifact_store import GcsPrefix, model_prefix


def test_parse_round_trip() -> None:
    p = GcsPrefix.parse("gs://bkt/a/b")
    assert p.bucket == "bkt"
    assert p.prefix == "a/b"
    assert p.uri() == "gs://bkt/a/b"


def test_parse_bucket_only() -> None:
    p = GcsPrefix.parse("gs://bkt")
    assert p.bucket == "bkt"
    assert p.prefix == ""
    assert p.uri() == "gs://bkt"


def test_parse_trailing_slash() -> None:
    p = GcsPrefix.parse("gs://bkt/a/b/")
    assert p.prefix == "a/b"


def test_child_and_uri() -> None:
    p = GcsPrefix.parse("gs://bkt/a")
    assert p.child("b").uri() == "gs://bkt/a/b"
    assert p.uri("c", "d") == "gs://bkt/a/c/d"


def test_model_prefix_layout() -> None:
    p = model_prefix(bucket="bkt", run_id="r1", date_str="2026-04-18")
    assert p.uri() == "gs://bkt/lgbm/2026-04-18/r1"
    assert p.uri("model.txt") == "gs://bkt/lgbm/2026-04-18/r1/model.txt"


def test_parse_rejects_non_gcs() -> None:
    import pytest

    with pytest.raises(ValueError):
        GcsPrefix.parse("s3://bkt/x")
