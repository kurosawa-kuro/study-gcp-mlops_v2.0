"""Port for query/passage embedding providers."""

from __future__ import annotations

from typing import Literal, Protocol


class EncoderClient(Protocol):
    """Embeds one text at a time for the hybrid-search serving path."""

    def embed(self, text: str, kind: Literal["query", "passage"]) -> list[float]: ...
