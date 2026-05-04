"""Pipeline-side adapters for ``data_job`` (embed pipeline)."""

from .in_memory_vector_search_writer import InMemoryVectorSearchWriter
from .vertex_vector_search_writer import VertexVectorSearchWriter

__all__ = [
    "InMemoryVectorSearchWriter",
    "VertexVectorSearchWriter",
]
