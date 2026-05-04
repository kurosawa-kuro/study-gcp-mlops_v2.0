"""Model artifact store (GCS-backed).

Implements:
    * :class:`GcsPrefix` — immutable URI builder for ``gs://bucket/prefix/...``
    * :func:`model_prefix` — canonical ``lgbm/{date}/{run_id}/`` layout
    * :func:`upload_directory` — recursive directory upload
    * :func:`download_file` — single-file download
    * :class:`ArtifactUploader` — Protocol used by the trainer
    * :class:`GcsArtifactUploader` — ArtifactUploader implementation

All heavy google-cloud-storage imports are deferred until call time so unit
tests can import this module without the SDK installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class GcsPrefix:
    bucket: str
    prefix: str  # no leading/trailing slash

    @classmethod
    def parse(cls, uri: str) -> GcsPrefix:
        if not uri.startswith("gs://"):
            raise ValueError(f"gcs uri must start with gs://: {uri!r}")
        bucket, _, prefix = uri[len("gs://") :].partition("/")
        if not bucket:
            raise ValueError(f"bucket missing in {uri!r}")
        return cls(bucket=bucket, prefix=prefix.strip("/"))

    def child(self, sub: str) -> GcsPrefix:
        new_prefix = "/".join(p for p in [self.prefix, sub.strip("/")] if p)
        return GcsPrefix(bucket=self.bucket, prefix=new_prefix)

    def uri(self, *parts: str) -> str:
        joined = "/".join(p.strip("/") for p in parts if p)
        base = f"gs://{self.bucket}"
        if self.prefix:
            base = f"{base}/{self.prefix}"
        return f"{base}/{joined}" if joined else base


def model_prefix(bucket: str, run_id: str, date_str: str) -> GcsPrefix:
    """Immutable model artifact prefix: lgbm/{YYYY-MM-DD}/{run_id}/."""
    return GcsPrefix(bucket=bucket, prefix=f"lgbm/{date_str}/{run_id}")


def upload_directory(local_dir: Path, destination: GcsPrefix) -> list[str]:
    from google.cloud import storage  # type: ignore[attr-defined]

    client = storage.Client()
    bucket = client.bucket(destination.bucket)
    uploaded: list[str] = []
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(local_dir).as_posix()
        blob_name = f"{destination.prefix}/{rel}" if destination.prefix else rel
        bucket.blob(blob_name).upload_from_filename(str(path))
        uploaded.append(f"gs://{destination.bucket}/{blob_name}")
    return uploaded


def download_file(gcs_uri: str, local_path: Path) -> Path:
    from google.cloud import storage  # type: ignore[attr-defined]

    prefix = GcsPrefix.parse(gcs_uri)
    client = storage.Client()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client.bucket(prefix.bucket).blob(prefix.prefix).download_to_filename(str(local_path))
    return local_path


class ArtifactUploader(Protocol):
    def upload(self, local_dir: Path, *, run_id: str, date_str: str) -> str:
        """Upload ``local_dir`` and return the resulting ``gs://.../model.txt`` URI."""
        ...


class GcsArtifactUploader:
    """Uploads artifacts under ``gs://{bucket}/lgbm/{date}/{run_id}/``."""

    def __init__(self, *, bucket: str) -> None:
        self._bucket = bucket

    def upload(self, local_dir: Path, *, run_id: str, date_str: str) -> str:
        dest = model_prefix(bucket=self._bucket, run_id=run_id, date_str=date_str)
        upload_directory(local_dir, dest)
        return dest.uri("model.txt")
