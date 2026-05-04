"""``VectorSearchWriter`` adapter — Vertex AI Vector Search (Phase 7 PR-3).

Wraps ``MatchingEngineIndex.upsert_datapoints`` so the embed pipeline
can push the latest ME5 embeddings into the deployed serving index after
the BigQuery MERGE has succeeded.

Production note: Vertex AI Vector Search supports both **stream** updates
(near-real-time, surcharged) and **batch** updates (cheaper, eventual
consistency). PR-3 uses streaming upsert via the SDK's
``upsert_datapoints`` API since the embed pipeline runs on a daily / hourly
cadence and the volume per run is bounded; switch to batch update via
GCS-staged JSONL when daily rebuilds exceed ~1M datapoints.

Tests inject ``index_factory`` to skip the real SDK import — same seam
as ``app/services/adapters/vertex_vector_search_semantic_search.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pipeline.data_job.ports.vector_search_writer import EmbeddingDatapoint

IndexFactory = Callable[[str], Any]
"""``index_factory(index_resource_name) -> MatchingEngineIndex``."""


class VertexVectorSearchWriter:
    """Phase 5+ production — ``MatchingEngineIndex.upsert_datapoints``.

    Args:
        index_resource_name: Fully-qualified resource name of the
            ``MatchingEngineIndex`` (NOT the index endpoint), e.g.
            ``projects/{p}/locations/{r}/indexes/{id}``.
        project: GCP project (used by ``aiplatform.init``).
        location: GCP region — must match the index's region.
        batch_size: Maximum datapoints sent per ``upsert_datapoints``
            call. Vertex Vector Search documents 1000 / call as the safe
            upper bound for streaming updates. Defaults to ``500``.
        index_factory: optional factory ``(name) -> MatchingEngineIndex``
            for tests. Production leaves ``None`` to lazy-import the
            real SDK.
    """

    def __init__(
        self,
        *,
        index_resource_name: str,
        project: str,
        location: str,
        batch_size: int = 500,
        index_factory: IndexFactory | None = None,
    ) -> None:
        if not index_resource_name:
            raise ValueError("index_resource_name is required")
        if not project:
            raise ValueError("project is required")
        if not location:
            raise ValueError("location is required")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._index_resource_name = index_resource_name
        self._project = project
        self._location = location
        self._batch_size = batch_size
        self._index_factory = index_factory
        self._index: Any | None = None
        self._datapoint_factory: Any | None = None

    def _resolve_index(self) -> Any:
        if self._index is not None:
            return self._index
        if self._index_factory is not None:
            self._index = self._index_factory(self._index_resource_name)
        else:
            from google.cloud import aiplatform  # lazy

            aiplatform.init(project=self._project, location=self._location)
            self._index = aiplatform.MatchingEngineIndex(index_name=self._index_resource_name)
        return self._index

    def upsert(self, datapoints: list[EmbeddingDatapoint]) -> None:
        if not datapoints:
            return
        index = self._resolve_index()
        for chunk in _chunked(datapoints, self._batch_size):
            payload = [self._to_sdk_datapoint(dp) for dp in chunk]
            index.upsert_datapoints(datapoints=payload)

    def _to_sdk_datapoint(self, dp: EmbeddingDatapoint) -> Any:
        # When ``index_factory`` was injected (tests), no SDK import was
        # performed; fall back to a duck-typed dict that the test index
        # can introspect. Production lazy-imports the proper proto type on
        # first call so we do not pay the SDK cost during unit tests.
        if self._datapoint_factory is None and self._index_factory is None:
            # GA ``aiplatform.MatchingEngineIndex.upsert_datapoints`` validates
            # the proto class as ``aiplatform_v1.types.IndexDatapoint``;
            # passing the v1beta1 variant raises
            # ``TypeError: Parameter to initialize message field must be ...
            # expected <class 'IndexDatapoint'> got
            # <class 'google.cloud.aiplatform_v1beta1.types.index.IndexDatapoint'>``.
            from google.cloud.aiplatform_v1.types import (  # lazy
                IndexDatapoint,
            )

            self._datapoint_factory = IndexDatapoint
        if self._datapoint_factory is None:
            return {"datapoint_id": dp.property_id, "feature_vector": list(dp.embedding)}
        return self._datapoint_factory(
            datapoint_id=dp.property_id,
            feature_vector=list(dp.embedding),
        )


def _chunked(items: list[EmbeddingDatapoint], size: int) -> list[list[EmbeddingDatapoint]]:
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[i : i + size] for i in range(0, len(items), size)]
