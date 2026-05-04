"""Domain models for the hybrid-search app.

Pure dataclasses / TypedDicts that describe the search domain (Candidate,
SearchFilters, SearchInput, SearchOutput). Independent of FastAPI Pydantic
schemas (`app/schemas/`) so the service layer can be exercised without HTTP
detail. ``app/services/protocols/`` Ports reference these domain types in
their signatures.

Per [`docs/conventions/フォルダ-ファイル.md`](../../../docs/conventions/フォルダ-ファイル.md): keep
domain models inside ``app/domain/`` rather than co-locating them with Ports
or schemas. Phase 7 design priority is **DI > Port-Adapter > Clean > Domain**
so we deliberately keep this lean — no Value Objects (Rent/Area/Address),
no Property entity. Add only when a concrete reuse forces it.
"""

from app.domain.candidate import Candidate, RankedCandidate
from app.domain.retrieval import LexicalResult, SemanticResult
from app.domain.search import (
    SearchFilters,
    SearchInput,
    SearchOutput,
    SearchResultItem,
)

__all__ = [
    "Candidate",
    "LexicalResult",
    "RankedCandidate",
    "SearchFilters",
    "SearchInput",
    "SearchOutput",
    "SearchResultItem",
    "SemanticResult",
]
