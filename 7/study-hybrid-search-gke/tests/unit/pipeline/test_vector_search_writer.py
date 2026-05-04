"""Unit tests for ``VectorSearchWriter`` adapters (Phase 7 PR-3).

Both adapters are exercised without importing
``google.cloud.aiplatform`` — ``VertexVectorSearchWriter`` accepts an
``index_factory`` injection, ``InMemoryVectorSearchWriter`` is pure
Python.

Phase 7 ``docs/tasks/TASKS_ROADMAP.md`` §3.3 受け入れ条件 (ローカル):
- mock で `MatchingEngineIndex.upsert_datapoints` を stub した unit test PASS
- ローカルで pipeline を fake adapter (BQ writer + VVS writer 両方 fake) で完走
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pipeline.data_job.adapters.in_memory_vector_search_writer import (
    InMemoryVectorSearchWriter,
)
from pipeline.data_job.adapters.vertex_vector_search_writer import (
    VertexVectorSearchWriter,
)
from pipeline.data_job.ports.vector_search_writer import EmbeddingDatapoint


def _datapoint(pid: str, value: float = 0.0, dim: int = 4) -> EmbeddingDatapoint:
    return EmbeddingDatapoint(property_id=pid, embedding=[value] * dim)


# ----------------------------------------------------------------------------
# InMemoryVectorSearchWriter
# ----------------------------------------------------------------------------


def test_in_memory_writer_records_datapoints() -> None:
    writer = InMemoryVectorSearchWriter()

    writer.upsert([_datapoint("p001", 0.1), _datapoint("p002", 0.2)])

    assert writer.datapoints == {
        "p001": [0.1, 0.1, 0.1, 0.1],
        "p002": [0.2, 0.2, 0.2, 0.2],
    }
    assert writer.upsert_calls == 1
    assert writer.batch_sizes == [2]


def test_in_memory_writer_is_idempotent() -> None:
    writer = InMemoryVectorSearchWriter()

    writer.upsert([_datapoint("p001", 0.1)])
    writer.upsert([_datapoint("p001", 0.5)])  # overwrite

    assert writer.datapoints == {"p001": [0.5, 0.5, 0.5, 0.5]}
    assert writer.upsert_calls == 2


def test_in_memory_writer_skips_empty_batch() -> None:
    writer = InMemoryVectorSearchWriter()
    writer.upsert([])
    assert writer.upsert_calls == 0
    assert writer.batch_sizes == []


# ----------------------------------------------------------------------------
# VertexVectorSearchWriter
# ----------------------------------------------------------------------------


def _index_with_recorder() -> tuple[Any, list[list[Any]]]:
    """Build a stub index whose ``upsert_datapoints`` records each call."""
    received: list[list[Any]] = []
    index = MagicMock()

    def _upsert(*, datapoints: list[Any]) -> None:
        received.append(list(datapoints))

    index.upsert_datapoints.side_effect = _upsert
    return index, received


def test_vertex_writer_calls_upsert_datapoints_with_payload() -> None:
    index, received = _index_with_recorder()
    writer = VertexVectorSearchWriter(
        index_resource_name="projects/x/locations/r/indexes/12345",
        project="x",
        location="r",
        index_factory=lambda _name: index,
    )

    writer.upsert([_datapoint("p001", 0.1), _datapoint("p002", 0.2)])

    assert len(received) == 1
    payload = received[0]
    assert {dp["datapoint_id"] for dp in payload} == {"p001", "p002"}
    p001 = next(dp for dp in payload if dp["datapoint_id"] == "p001")
    assert p001["feature_vector"] == [0.1, 0.1, 0.1, 0.1]


def test_vertex_writer_chunks_large_batches() -> None:
    index, received = _index_with_recorder()
    writer = VertexVectorSearchWriter(
        index_resource_name="projects/x/locations/r/indexes/12345",
        project="x",
        location="r",
        batch_size=2,
        index_factory=lambda _name: index,
    )

    writer.upsert(
        [
            _datapoint("p001"),
            _datapoint("p002"),
            _datapoint("p003"),
            _datapoint("p004"),
            _datapoint("p005"),
        ]
    )

    # 5 datapoints / 2 per batch → 3 calls (2, 2, 1)
    assert [len(batch) for batch in received] == [2, 2, 1]


def test_vertex_writer_skips_empty_batch() -> None:
    index = MagicMock()
    writer = VertexVectorSearchWriter(
        index_resource_name="projects/x/locations/r/indexes/12345",
        project="x",
        location="r",
        index_factory=lambda _name: index,
    )

    writer.upsert([])

    index.upsert_datapoints.assert_not_called()


def test_vertex_writer_resolves_index_once() -> None:
    seen: list[str] = []

    def factory(name: str) -> Any:
        seen.append(name)
        index, _received = _index_with_recorder()
        return index

    writer = VertexVectorSearchWriter(
        index_resource_name="projects/x/locations/r/indexes/12345",
        project="x",
        location="r",
        index_factory=factory,
    )
    writer.upsert([_datapoint("p001")])
    writer.upsert([_datapoint("p002")])

    assert seen == ["projects/x/locations/r/indexes/12345"]


@pytest.mark.parametrize(
    ("kwargs", "missing"),
    [
        ({"index_resource_name": ""}, "index_resource_name"),
        ({"project": ""}, "project"),
        ({"location": ""}, "location"),
        ({"batch_size": 0}, "batch_size"),
        ({"batch_size": -1}, "batch_size"),
    ],
)
def test_vertex_writer_rejects_invalid_args(kwargs: dict[str, object], missing: str) -> None:
    base: dict[str, object] = {
        "index_resource_name": "projects/x/locations/r/indexes/12345",
        "project": "x",
        "location": "r",
        "batch_size": 500,
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=missing):
        VertexVectorSearchWriter(**base)  # type: ignore[arg-type]
