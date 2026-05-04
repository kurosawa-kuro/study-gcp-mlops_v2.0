"""Pure orchestration for the embedding-job.

Given (a) a :class:`PropertyTextRepository`, (b) an :class:`EmbeddingStore`,
(c) an :class:`E5Encoder`, re-encode only the property rows whose
``text_hash`` changed (or is absent from the store). Returns the number of
upserted rows so the CLI can surface it in logs.

Kept free of GCP SDK imports so pipeline components can re-use it.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Protocol

from ml.data.loaders.embedding_store import (
    EmbeddingRow,
    EmbeddingStore,
    PropertyText,
    PropertyTextRepository,
)
from ml.serving.encoder import E5Encoder


class _Logger(Protocol):
    def info(self, msg: str, *args: object) -> None: ...


def _text_for_embedding(p: PropertyText) -> str:
    title = p.title or ""
    description = p.description or ""
    return f"{title}。{description}".strip()


def _hash(text: str, model_name: str) -> str:
    h = hashlib.sha256()
    h.update(model_name.encode("utf-8"))
    h.update(b"\x1f")  # unit separator to prevent concat collisions
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def run_embedding_batch(
    *,
    repository: PropertyTextRepository,
    store: EmbeddingStore,
    encoder: E5Encoder,
    logger: _Logger,
    batch_size: int = 64,
    now: datetime | None = None,
) -> int:
    """Encode + upsert only the changed rows; return the count written."""
    generated_at = now or datetime.now(timezone.utc)
    existing = store.existing_hashes()
    properties = repository.fetch_all()
    to_encode: list[PropertyText] = []
    for p in properties:
        text = _text_for_embedding(p)
        h = _hash(text, encoder.model_name)
        if existing.get(p.property_id) == h:
            continue
        to_encode.append(p)
    logger.info(
        "Embedding run: %d total / %d unchanged / %d to encode",
        len(properties),
        len(properties) - len(to_encode),
        len(to_encode),
    )

    pending: list[EmbeddingRow] = []
    total_written = 0
    for offset in range(0, len(to_encode), batch_size):
        batch = to_encode[offset : offset + batch_size]
        texts = [_text_for_embedding(p) for p in batch]
        vectors = encoder.encode_passages(texts)
        for p, vec in zip(batch, vectors, strict=True):
            pending.append(
                EmbeddingRow(
                    property_id=p.property_id,
                    embedding=[float(x) for x in vec],
                    text_hash=_hash(_text_for_embedding(p), encoder.model_name),
                    model_name=encoder.model_name,
                    generated_at=generated_at,
                )
            )
        total_written += store.upsert(pending)
        pending = []
    return total_written
