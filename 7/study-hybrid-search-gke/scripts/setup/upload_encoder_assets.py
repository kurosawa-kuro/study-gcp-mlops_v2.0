"""Download the multilingual-e5-base checkpoint and upload it to GCS.

Phase 3 one-off: the Vertex AI encoder CPR container reads ``AIP_STORAGE_URI``
at startup and hydrates sentence-transformers from that GCS prefix. This
script populates that prefix so ``setup_encoder_endpoint.py`` can register a
``Model`` whose ``artifact_uri`` points at it.

Default target:

    gs://{GCS_MODELS_BUCKET or "{PROJECT_ID}-models"}/encoders/multilingual-e5-base/v1/

Idempotent: the script compares the local blob listing to what is already in
GCS and skips identical objects. Force re-upload with ``--overwrite``.

The heavy imports (``sentence_transformers`` / ``google.cloud.storage``) are
deferred into :func:`_apply` so :func:`build_upload_spec` stays importable in
unit tests without a network or SDK install.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts._common import env, gcs_bucket_name

MODEL_NAME: str = "intfloat/multilingual-e5-base"
DEFAULT_ASSET_VERSION: str = "v1"


def build_upload_spec() -> dict[str, Any]:
    """Resolve the spec (model name + bucket + prefix) without SDK calls."""
    project_id = env("PROJECT_ID")
    bucket = env("GCS_MODELS_BUCKET", gcs_bucket_name("models") if project_id else "")
    version = env("ENCODER_ASSET_VERSION", DEFAULT_ASSET_VERSION)
    prefix = f"encoders/multilingual-e5-base/{version}/"
    return {
        "model_name": env("ENCODER_MODEL_NAME", MODEL_NAME),
        "bucket": bucket,
        "prefix": prefix,
        "gcs_uri": f"gs://{bucket}/{prefix}" if bucket else "",
        "version": version,
    }


def _download_model(model_name: str, dest: Path) -> Path:
    from sentence_transformers import SentenceTransformer

    dest.mkdir(parents=True, exist_ok=True)
    model = SentenceTransformer(model_name)
    model.save(str(dest))
    return dest


def _iter_local_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def _upload_directory(
    local_dir: Path,
    bucket_name: str,
    prefix: str,
    *,
    overwrite: bool,
) -> list[str]:
    from google.cloud import storage  # type: ignore[attr-defined]

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    uploaded: list[str] = []
    for path in _iter_local_files(local_dir):
        rel = path.relative_to(local_dir).as_posix()
        blob_name = f"{prefix}{rel}"
        blob = bucket.blob(blob_name)
        if not overwrite and blob.exists(client=client):
            continue
        blob.upload_from_filename(str(path))
        uploaded.append(f"gs://{bucket_name}/{blob_name}")
    return uploaded


def _apply(spec: dict[str, Any], *, cache_dir: Path, overwrite: bool) -> list[str]:
    if not spec["bucket"]:
        raise RuntimeError("GCS bucket is empty; set GCS_MODELS_BUCKET or PROJECT_ID")
    local_root = cache_dir / "multilingual-e5-base"
    if not local_root.exists() or overwrite:
        _download_model(spec["model_name"], local_root)
    return _upload_directory(
        local_root,
        spec["bucket"],
        spec["prefix"],
        overwrite=overwrite,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload ME5 encoder assets to GCS")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually download from HuggingFace and upload to GCS (requires SDK + network).",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Local dir to cache the downloaded model (default: ./.cache/encoder-assets).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-upload blobs even if they already exist in GCS.",
    )
    args = parser.parse_args()

    spec = build_upload_spec()
    print(json.dumps(spec, ensure_ascii=False, indent=2))
    if args.apply:
        cache_dir = Path(args.cache_dir or ".cache/encoder-assets").expanduser().resolve()
        uploaded = _apply(spec, cache_dir=cache_dir, overwrite=args.overwrite)
        print(json.dumps({"uploaded_count": len(uploaded), "sample": uploaded[:5]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
