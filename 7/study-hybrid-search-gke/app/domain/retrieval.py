"""Value objects for retrieval-layer results."""

from __future__ import annotations

from typing import NamedTuple


class LexicalResult(NamedTuple):
    property_id: str
    rank: int


class SemanticResult(NamedTuple):
    property_id: str
    rank: int
    similarity: float
