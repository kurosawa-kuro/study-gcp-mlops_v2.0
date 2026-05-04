"""Port for upserting embeddings to a serving-side vector store (Phase 7 PR-3).

The embed pipeline writes the canonical embedding rows to BigQuery
``feature_mart.property_embeddings`` (existing ``write_embeddings``
component). This Port abstracts the **serving-side** push to a vector
ANN index — production target is Vertex AI Vector Search, but adapters
for in-memory / file-system fakes are available for local pipeline runs.

Failure semantics:
    Implementations may raise on transport / quota / auth errors. The
    embed DAG runs the upsert step **after** the BQ MERGE, so a failed
    upsert does not roll back the canonical store; ops sees the failure
    via Cloud Logging structured ERROR + the eventual consistency gap is
    closed by the next pipeline run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingDatapoint:
    """One ID/vector pair to upsert into the serving-side index.

    ``embedding`` must match the index's configured dimensionality (768
    for ``intfloat/multilingual-e5-base``, locked in
    ``ml/common/config/embedding.py`` and the BigQuery
    ``property_embeddings.embedding`` schema).
    """

    property_id: str
    embedding: list[float]


class VectorSearchWriter(Protocol):
    """Upsert a batch of ``(property_id, embedding)`` pairs to the index.

    ``upsert`` is idempotent: calling it twice with the same datapoints
    should leave the index in the same state. Implementations may
    internally chunk large batches; callers pass the full batch.
    """

    def upsert(self, datapoints: list[EmbeddingDatapoint]) -> None: ...
