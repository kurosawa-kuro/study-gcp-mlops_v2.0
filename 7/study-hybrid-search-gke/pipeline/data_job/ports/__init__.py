"""Pipeline-side Ports for ``data_job`` (embed pipeline).

Phase 7 PR-3 introduces ``VectorSearchWriter`` — the Port for upserting
embeddings to a serving-side vector store (Vertex AI Vector Search index
in production). The BigQuery embedding table remains the canonical source
of truth; this Port abstracts the serving-side push so the embed pipeline
can be re-targeted at a different ANN backend later by adapter swap only.
"""

from .vector_search_writer import EmbeddingDatapoint, VectorSearchWriter

__all__ = [
    "EmbeddingDatapoint",
    "VectorSearchWriter",
]
