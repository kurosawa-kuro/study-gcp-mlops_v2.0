"""``SemanticSearchPort`` adapter — Vertex AI Vector Search match endpoint.

Phase 5+ production serving index (PR-1 of `docs/tasks/TASKS_ROADMAP.md` Wave 1).
The canonical embedding generation history / metadata stays in BigQuery
``feature_mart.property_embeddings``; this adapter only queries the deployed
serving index for ANN top-K and returns ``SemanticResult`` named-tuples.

Filter pushdown:
    Vertex AI Vector Search supports ``restricts`` (categorical tags) and
    ``numeric_restricts`` (numeric ranges) at query time, but those require
    the index to be built with the corresponding metadata. PR-1 does NOT
    implement pushdown — ``filters`` received here are intentionally ignored
    at the ANN layer, and ``BigQueryCandidateRetriever._enrich_from_bq``
    downstream re-applies attribute filters via BigQuery joins on
    ``properties_cleaned``. Track in roadmap §3.1 follow-up if this becomes
    a performance issue (fix = build the index with metadata + pass
    restricts here).

Distance metric:
    Assumes the deployed index uses ``COSINE_DISTANCE`` (matches the BigQuery
    ``VECTOR_SEARCH(..., distance_type => 'COSINE')`` contract used in
    ``BigQuerySemanticSearch``). Similarity is reported as ``1.0 - distance``
    so values land in ``[0, 1]`` with higher = more similar, identical to
    the Phase 5 BigQuery adapter.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.domain.retrieval import SemanticResult
from app.domain.search import SearchFilters

EndpointFactory = Callable[[str], Any]


class VertexVectorSearchSemanticSearch:
    """Phase 5+ production — Vertex AI Vector Search ``find_neighbors``.

    Args:
        index_endpoint_name: Fully-qualified resource name of the deployed
            Vertex AI Index Endpoint, e.g.
            ``projects/{project}/locations/{region}/indexEndpoints/{id}``.
        deployed_index_id: ``DeployedIndex.id`` published on the endpoint
            (matches the ID surfaced by
            ``MatchingEngineIndexEndpoint.deployed_indexes``).
        project: GCP project (used by ``aiplatform.init``).
        location: GCP region — must equal the region the index is deployed
            in (typically ``asia-northeast1`` per Phase 7 non-負 constraint).
        endpoint_factory: optional callable
            ``index_endpoint_name -> MatchingEngineIndexEndpoint``. Tests
            inject a mock here to avoid importing
            ``google.cloud.aiplatform`` and to keep unit tests free of
            credentials. Production leaves this ``None`` so the adapter
            lazy-imports the real SDK on first use.
    """

    def __init__(
        self,
        *,
        index_endpoint_name: str,
        deployed_index_id: str,
        project: str,
        location: str,
        endpoint_factory: EndpointFactory | None = None,
    ) -> None:
        if not index_endpoint_name:
            raise ValueError("index_endpoint_name is required")
        if not deployed_index_id:
            raise ValueError("deployed_index_id is required")
        if not project:
            raise ValueError("project is required")
        if not location:
            raise ValueError("location is required")
        self._index_endpoint_name = index_endpoint_name
        self._deployed_index_id = deployed_index_id
        self._project = project
        self._location = location
        self._endpoint_factory = endpoint_factory
        self._endpoint: Any | None = None

    def _resolve_endpoint(self) -> Any:
        if self._endpoint is not None:
            return self._endpoint
        if self._endpoint_factory is not None:
            self._endpoint = self._endpoint_factory(self._index_endpoint_name)
        else:
            from google.cloud import aiplatform  # lazy import — keeps unit tests cheap

            aiplatform.init(project=self._project, location=self._location)
            self._endpoint = aiplatform.MatchingEngineIndexEndpoint(
                index_endpoint_name=self._index_endpoint_name
            )
        return self._endpoint

    def search(
        self,
        *,
        query_vector: list[float],
        filters: SearchFilters,
        top_k: int,
    ) -> list[SemanticResult]:
        # ``filters`` is part of the ``SemanticSearchPort`` contract but PR-1
        # does not push down to the ANN layer (see module docstring); re-bind
        # to ``_`` to silence ARG002 without losing the public signature.
        _ = filters
        endpoint = self._resolve_endpoint()
        response = endpoint.find_neighbors(
            deployed_index_id=self._deployed_index_id,
            queries=[query_vector],
            num_neighbors=top_k,
        )
        if not response:
            return []
        neighbors = response[0]
        out: list[SemanticResult] = []
        for rank, neighbor in enumerate(neighbors, start=1):
            distance = getattr(neighbor, "distance", 1.0)
            similarity = 1.0 - float(distance)
            out.append(
                SemanticResult(
                    property_id=str(neighbor.id),
                    rank=rank,
                    similarity=similarity,
                )
            )
        return out
