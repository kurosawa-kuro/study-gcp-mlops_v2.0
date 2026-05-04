"""Unit tests for ``VertexVectorSearchSemanticSearch`` adapter (Phase 7 PR-1).

Covers the adapter contract without importing or hitting
``google.cloud.aiplatform`` — tests inject ``endpoint_factory`` to satisfy
the lazy-import seam, so ``make check`` runs offline.

Phase 7 ``docs/tasks/TASKS_ROADMAP.md`` §3.1 受け入れ条件 (ローカル):
- mock で Vertex SDK call を stub した unit test PASS
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.domain.retrieval import SemanticResult
from app.domain.search import SearchFilters
from app.services.adapters.vertex_vector_search_semantic_search import (
    VertexVectorSearchSemanticSearch,
)


def _make_neighbor(neighbor_id: str, distance: float) -> Any:
    """Mimic the ``MatchNeighbor`` shape returned by ``find_neighbors``.

    The real type lives at
    ``google.cloud.aiplatform.matching_engine.matching_engine_index_endpoint.MatchNeighbor``.
    Only ``.id`` and ``.distance`` are used by the adapter.
    """
    neighbor = MagicMock()
    neighbor.id = neighbor_id
    neighbor.distance = distance
    return neighbor


def _factory_returning(*neighbors: Any) -> Any:
    """Build an ``endpoint_factory`` that yields a single-query response."""
    endpoint = MagicMock()
    endpoint.find_neighbors.return_value = [list(neighbors)]
    return lambda _name: endpoint


def _adapter(factory: Any) -> VertexVectorSearchSemanticSearch:
    return VertexVectorSearchSemanticSearch(
        index_endpoint_name="projects/x/locations/asia-northeast1/indexEndpoints/12345",
        deployed_index_id="property_embeddings_v3",
        project="x",
        location="asia-northeast1",
        endpoint_factory=factory,
    )


# ----------------------------------------------------------------------------
# Behaviour
# ----------------------------------------------------------------------------


def test_search_converts_neighbors_to_semantic_results_in_distance_order() -> None:
    factory = _factory_returning(
        _make_neighbor("p001", 0.10),
        _make_neighbor("p002", 0.25),
        _make_neighbor("p003", 0.50),
    )
    adapter = _adapter(factory)

    results = adapter.search(
        query_vector=[0.0] * 768,
        filters=SearchFilters(),
        top_k=3,
    )

    assert results == [
        SemanticResult(property_id="p001", rank=1, similarity=pytest.approx(0.90)),
        SemanticResult(property_id="p002", rank=2, similarity=pytest.approx(0.75)),
        SemanticResult(property_id="p003", rank=3, similarity=pytest.approx(0.50)),
    ]


def test_search_returns_empty_when_no_neighbors() -> None:
    adapter = _adapter(_factory_returning())
    assert adapter.search(query_vector=[0.0] * 768, filters=SearchFilters(), top_k=10) == []


def test_search_returns_empty_when_response_is_empty() -> None:
    """Defensive: ``find_neighbors`` could return ``[]`` (no inner list)."""
    endpoint = MagicMock()
    endpoint.find_neighbors.return_value = []
    adapter = VertexVectorSearchSemanticSearch(
        index_endpoint_name="projects/x/locations/asia-northeast1/indexEndpoints/12345",
        deployed_index_id="property_embeddings_v3",
        project="x",
        location="asia-northeast1",
        endpoint_factory=lambda _name: endpoint,
    )
    assert adapter.search(query_vector=[0.0] * 768, filters=SearchFilters(), top_k=10) == []


def test_search_passes_top_k_and_query_vector_and_deployed_index_id() -> None:
    endpoint = MagicMock()
    endpoint.find_neighbors.return_value = [[]]
    adapter = VertexVectorSearchSemanticSearch(
        index_endpoint_name="projects/x/locations/asia-northeast1/indexEndpoints/12345",
        deployed_index_id="property_embeddings_v3",
        project="x",
        location="asia-northeast1",
        endpoint_factory=lambda _name: endpoint,
    )

    adapter.search(query_vector=[0.1] * 768, filters=SearchFilters(), top_k=42)

    endpoint.find_neighbors.assert_called_once_with(
        deployed_index_id="property_embeddings_v3",
        queries=[[0.1] * 768],
        num_neighbors=42,
    )


def test_search_ignores_filters_in_pr1_known_limitation() -> None:
    """PR-1 does NOT pushdown filters to the ANN layer (see module docstring).

    Verify that passing arbitrary filters does not affect the call. Filter
    pushdown is roadmap §3.1 follow-up work.
    """
    endpoint = MagicMock()
    endpoint.find_neighbors.return_value = [[]]
    adapter = VertexVectorSearchSemanticSearch(
        index_endpoint_name="projects/x/locations/asia-northeast1/indexEndpoints/12345",
        deployed_index_id="property_embeddings_v3",
        project="x",
        location="asia-northeast1",
        endpoint_factory=lambda _name: endpoint,
    )

    adapter.search(
        query_vector=[0.1] * 768,
        filters=SearchFilters(max_rent=80000, layout="2LDK", pet_ok=True),
        top_k=10,
    )

    call_kwargs = endpoint.find_neighbors.call_args.kwargs
    # Filter values must not leak into the find_neighbors call (no pushdown yet).
    assert "filter" not in call_kwargs
    assert "restricts" not in call_kwargs
    assert "numeric_restricts" not in call_kwargs


def test_endpoint_factory_called_with_resource_name_once() -> None:
    """The lazy-resolution of the endpoint must happen at most once and
    receive the configured ``index_endpoint_name`` verbatim.
    """
    seen: list[str] = []

    def factory(name: str) -> Any:
        seen.append(name)
        endpoint = MagicMock()
        endpoint.find_neighbors.return_value = [[]]
        return endpoint

    adapter = VertexVectorSearchSemanticSearch(
        index_endpoint_name="projects/x/locations/asia-northeast1/indexEndpoints/12345",
        deployed_index_id="property_embeddings_v3",
        project="x",
        location="asia-northeast1",
        endpoint_factory=factory,
    )
    adapter.search(query_vector=[0.0] * 768, filters=SearchFilters(), top_k=1)
    adapter.search(query_vector=[0.0] * 768, filters=SearchFilters(), top_k=1)

    assert seen == ["projects/x/locations/asia-northeast1/indexEndpoints/12345"]


def test_search_handles_missing_distance_attribute_as_max_distance() -> None:
    """If ``MatchNeighbor.distance`` is missing, similarity should default to
    0.0 (1 - max_distance) so a malformed response does not silently boost
    the candidate's RRF score. Mirrors the BQ adapter's ``or 1.0`` guard.
    """
    bad_neighbor = MagicMock(spec=["id"])  # only ``id`` attribute exists
    bad_neighbor.id = "p999"
    adapter = _adapter(_factory_returning(bad_neighbor))

    results = adapter.search(query_vector=[0.0] * 768, filters=SearchFilters(), top_k=1)

    assert results == [SemanticResult(property_id="p999", rank=1, similarity=0.0)]


# ----------------------------------------------------------------------------
# Constructor validation
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "missing"),
    [
        ({"index_endpoint_name": ""}, "index_endpoint_name"),
        ({"deployed_index_id": ""}, "deployed_index_id"),
        ({"project": ""}, "project"),
        ({"location": ""}, "location"),
    ],
)
def test_constructor_rejects_empty_required_args(kwargs: dict[str, str], missing: str) -> None:
    base: dict[str, str] = {
        "index_endpoint_name": "projects/x/locations/r/indexEndpoints/1",
        "deployed_index_id": "d",
        "project": "x",
        "location": "r",
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=missing):
        VertexVectorSearchSemanticSearch(**base)  # type: ignore[arg-type]
