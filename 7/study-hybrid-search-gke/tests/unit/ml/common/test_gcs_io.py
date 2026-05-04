"""Happy-path tests for gcs_artifact_store.upload_directory / download_file.

google.cloud.storage.Client is mocked — no network calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from ml.registry.artifact_store import GcsPrefix, download_file, upload_directory


def test_upload_directory_recurses_and_returns_uris(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("b")

    fake_blob = MagicMock()
    fake_bucket = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket

    dest = GcsPrefix(bucket="bkt", prefix="lgbm/2026-04-18/r1")
    with patch("google.cloud.storage.Client", return_value=fake_client):
        uris = upload_directory(tmp_path, dest)

    assert sorted(uris) == [
        "gs://bkt/lgbm/2026-04-18/r1/a.txt",
        "gs://bkt/lgbm/2026-04-18/r1/sub/b.txt",
    ]
    fake_client.bucket.assert_called_once_with("bkt")
    # Two files → two blob() calls with full prefixed paths
    blob_names = {c.args[0] for c in fake_bucket.blob.call_args_list}
    assert blob_names == {
        "lgbm/2026-04-18/r1/a.txt",
        "lgbm/2026-04-18/r1/sub/b.txt",
    }
    assert fake_blob.upload_from_filename.call_count == 2


def test_upload_directory_handles_empty_prefix(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x")

    fake_blob = MagicMock()
    fake_bucket = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket

    dest = GcsPrefix(bucket="bkt", prefix="")
    with patch("google.cloud.storage.Client", return_value=fake_client):
        uris = upload_directory(tmp_path, dest)

    assert uris == ["gs://bkt/f.txt"]
    fake_bucket.blob.assert_called_once_with("f.txt")


def test_download_file_writes_to_local_path(tmp_path: Path) -> None:
    fake_blob = MagicMock()
    fake_bucket = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_client = MagicMock()
    fake_client.bucket.return_value = fake_bucket

    target = tmp_path / "nested" / "model.txt"
    with patch("google.cloud.storage.Client", return_value=fake_client):
        returned = download_file("gs://bkt/lgbm/d/r/model.txt", target)

    assert returned == target
    assert target.parent.exists()
    fake_client.bucket.assert_called_once_with("bkt")
    fake_bucket.blob.assert_called_once_with("lgbm/d/r/model.txt")
    fake_blob.download_to_filename.assert_called_once_with(str(target))
