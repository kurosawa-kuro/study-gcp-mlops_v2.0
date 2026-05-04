"""Deterministic ``EncoderClient`` stub for service-layer tests."""

from __future__ import annotations

from typing import Literal

from app.services.protocols.encoder_client import EncoderClient


class StubEncoderClient(EncoderClient):
    """Returns a fixed embedding regardless of input text.

    Default vector is the unit basis ``[1, 0, 0, ...]`` of dimension 768
    (the multilingual-e5-base contract). Tests that need a specific
    embedding can pass ``embedding=...``. Records every call on
    ``self.calls`` so behaviour can be asserted (``len(calls)``,
    ``calls[0].text``).
    """

    def __init__(
        self,
        *,
        embedding: list[float] | None = None,
        embedding_dim: int = 768,
    ) -> None:
        if embedding is None:
            embedding = [1.0] + [0.0] * (embedding_dim - 1)
        self._embedding = list(embedding)
        self.endpoint_name = "stub-encoder"
        self.calls: list[_EncoderCall] = []

    def embed(self, text: str, kind: Literal["query", "passage"]) -> list[float]:
        self.calls.append(_EncoderCall(text=text, kind=kind))
        return list(self._embedding)


class _EncoderCall:
    __slots__ = ("kind", "text")

    def __init__(self, *, text: str, kind: str) -> None:
        self.text = text
        self.kind = kind

    def __repr__(self) -> str:
        return f"_EncoderCall(text={self.text!r}, kind={self.kind!r})"
