"""In-memory ``VectorSearchWriter`` for local pipeline runs / tests.

Stores all upserted datapoints in a dict keyed by ``property_id`` so
later upserts overwrite (idempotent). Records the number of upsert calls
so tests can assert batching behaviour.
"""

from __future__ import annotations

from pipeline.data_job.ports.vector_search_writer import EmbeddingDatapoint


class InMemoryVectorSearchWriter:
    """Idempotent in-memory upsert; useful for local / test pipeline runs."""

    def __init__(self) -> None:
        self.datapoints: dict[str, list[float]] = {}
        self.upsert_calls: int = 0
        self.batch_sizes: list[int] = []

    def upsert(self, datapoints: list[EmbeddingDatapoint]) -> None:
        if not datapoints:
            return
        self.upsert_calls += 1
        self.batch_sizes.append(len(datapoints))
        for dp in datapoints:
            self.datapoints[dp.property_id] = list(dp.embedding)
