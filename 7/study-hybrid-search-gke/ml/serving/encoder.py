"""multilingual-e5-base encoder model + local/dev prediction routine.

ME5 models require the prompt prefix on every input:

* queries  → ``"query: ..."``
* passages → ``"passage: ..."``

Mixing them silently drops retrieval quality by several NDCG points. Keep the
helpers :func:`encode_query` / :func:`encode_passage` as the only entry points.

Heavy dependencies (``sentence_transformers``) are imported lazily inside
:meth:`E5Encoder.load`, so unit tests + composition roots that stub the
``model`` attribute do not need torch installed.

Runtime-compat note:

* production Phase 7 uses KServe HuggingFace runtime and sends
  ``{"instances": ["query: ..."]}``
* older/local CPR callers may still send
  ``{"instances": [{"text": "...", "kind": "query"}]}``

This server accepts both so local dev does not drift from the app-side
``KServeEncoder`` contract.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ml.registry.artifact_store import GcsPrefix, download_file

E5_MODEL_NAME: str = "intfloat/multilingual-e5-base"
E5_VECTOR_DIM: int = 768

QUERY_PREFIX: str = "query: "
PASSAGE_PREFIX: str = "passage: "


@dataclass
class E5Encoder:
    """Thin wrapper around a sentence-transformers model with ME5 prefixes."""

    model: Any
    model_name: str = E5_MODEL_NAME
    vector_dim: int = E5_VECTOR_DIM

    @classmethod
    def load(cls, *, model_source: str | Path | None = None) -> E5Encoder:
        """Instantiate a real sentence-transformers encoder.

        ``model_source`` may be a local directory or a Hugging Face model ID.
        ``None`` falls back to ``intfloat/multilingual-e5-base``.
        """
        from sentence_transformers import SentenceTransformer

        path = str(model_source) if model_source is not None else E5_MODEL_NAME
        model = SentenceTransformer(path)
        return cls(model=model)

    def _encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype=float)

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        return self._encode([QUERY_PREFIX + q for q in queries])

    def encode_passages(self, passages: list[str]) -> np.ndarray:
        return self._encode([PASSAGE_PREFIX + p for p in passages])


def encode_query(encoder: E5Encoder, query: str) -> np.ndarray:
    return np.asarray(encoder.encode_queries([query])[0])


def encode_passage(encoder: E5Encoder, passage: str) -> np.ndarray:
    return np.asarray(encoder.encode_passages([passage])[0])


class EncoderInstance(BaseModel):
    text: str = Field(min_length=1)
    kind: str = Field(pattern="^(query|passage)$")


class EncoderRequest(BaseModel):
    instances: list[EncoderInstance | str]


class EncoderResponse(BaseModel):
    predictions: list[list[float]]


def _download_artifact_dir(gcs_uri: str, workdir: Path) -> Path:
    # GcsPrefix.parse() は trailing slash を strip する仕様 (artifact_store.py の
    # `prefix.strip("/")`)。ここでは strip 後の prefix をそのまま list_blobs の
    # prefix 引数に渡し、各 blob の name から切り出して download する。
    # prefix が (末尾スラッシュ有無にかかわらず) ディレクトリを指していることは
    # Vertex が AIP_STORAGE_URI として保証する運用前提とする。
    prefix = GcsPrefix.parse(gcs_uri)
    local_root = workdir / "model"
    local_root.mkdir(parents=True, exist_ok=True)
    from google.cloud import storage  # type: ignore[attr-defined]

    # list_blobs の prefix は directory として扱うため末尾 `/` を付ける。
    # 先頭 `blob.name` から prefix_with_slash を剥がして相対パスに変換する。
    prefix_with_slash = f"{prefix.prefix}/" if prefix.prefix else ""
    client = storage.Client()
    for blob in client.list_blobs(prefix.bucket, prefix=prefix_with_slash):
        if blob.name.endswith("/"):
            continue
        rel = blob.name[len(prefix_with_slash) :] if prefix_with_slash else blob.name
        download_file(f"gs://{prefix.bucket}/{blob.name}", local_root / rel)
    return local_root


def _load_encoder() -> E5Encoder:
    local_model_dir = os.getenv("LOCAL_ENCODER_MODEL_DIR", "").strip()
    if local_model_dir:
        return E5Encoder.load(model_source=Path(local_model_dir))
    storage_uri = os.getenv("AIP_STORAGE_URI", "").strip()
    if storage_uri:
        tmpdir = Path(tempfile.mkdtemp(prefix="encoder-model-"))
        model_dir = _download_artifact_dir(storage_uri, tmpdir)
        return E5Encoder.load(model_source=model_dir)
    model_name = os.getenv("ENCODER_MODEL_NAME", E5_MODEL_NAME).strip() or E5_MODEL_NAME
    return E5Encoder.load(model_source=model_name)


def _normalize_instance(item: EncoderInstance | str) -> str:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            raise ValueError("encoder instance must not be empty")
        if text.startswith(QUERY_PREFIX) or text.startswith(PASSAGE_PREFIX):
            return text
        return QUERY_PREFIX + text
    return f"{item.kind}: {item.text.strip()}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.encoder = _load_encoder()
    yield


app = FastAPI(title="vertex-encoder-server", lifespan=lifespan)
app.state.encoder = None


@app.get(os.getenv("AIP_HEALTH_ROUTE", "/health"))
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(os.getenv("AIP_PREDICT_ROUTE", "/predict"), response_model=EncoderResponse)
def predict(request: EncoderRequest) -> EncoderResponse:
    encoder: E5Encoder | None = app.state.encoder
    if encoder is None:
        raise HTTPException(status_code=503, detail="encoder not loaded")
    try:
        normalized = [_normalize_instance(item) for item in request.instances]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    vectors = encoder._encode(normalized).tolist()
    return EncoderResponse(predictions=[[float(v) for v in row] for row in vectors])


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("AIP_HTTP_PORT", os.getenv("PORT", "8080"))),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
