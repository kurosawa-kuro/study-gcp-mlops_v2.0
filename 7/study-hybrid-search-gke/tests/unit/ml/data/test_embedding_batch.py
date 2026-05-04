"""Embedding runner smoke test — change detection + upsert loop."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ml.data.datasets.embedding_batch import run_embedding_batch
from ml.data.loaders.embedding_store import EmbeddingRow, PropertyText


@dataclass
class _FakeEncoder:
    model_name: str = "fake-e5"

    def encode_passages(self, passages: list[str]) -> np.ndarray:
        return np.array([[len(p), 1.0, 2.0] for p in passages], dtype=float)

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        return self.encode_passages(queries)


@dataclass
class _FakeRepo:
    rows: list[PropertyText]

    def fetch_all(self) -> list[PropertyText]:
        return list(self.rows)


@dataclass
class _FakeStore:
    by_id: dict[str, EmbeddingRow] = field(default_factory=dict)

    def existing_hashes(self) -> dict[str, str]:
        return {pid: row.text_hash for pid, row in self.by_id.items()}

    def upsert(self, rows: list[EmbeddingRow]) -> int:
        for r in rows:
            self.by_id[r.property_id] = r
        return len(rows)


class _CaptureLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, msg: str, *args: object) -> None:
        self.messages.append(msg % args if args else msg)


def test_encodes_all_on_empty_store() -> None:
    repo = _FakeRepo(
        rows=[
            PropertyText(property_id="P1", title="タイトル1", description="説明1"),
            PropertyText(property_id="P2", title="タイトル2", description="説明2"),
        ]
    )
    store = _FakeStore()
    encoder = _FakeEncoder()
    written = run_embedding_batch(
        repository=repo, store=store, encoder=encoder, logger=_CaptureLogger()
    )
    assert written == 2
    assert set(store.by_id) == {"P1", "P2"}


def test_skips_unchanged_rows_on_rerun() -> None:
    repo = _FakeRepo(rows=[PropertyText(property_id="P1", title="A", description="B")])
    store = _FakeStore()
    encoder = _FakeEncoder()
    log = _CaptureLogger()
    first = run_embedding_batch(repository=repo, store=store, encoder=encoder, logger=log)
    assert first == 1
    second = run_embedding_batch(repository=repo, store=store, encoder=encoder, logger=log)
    assert second == 0


def test_re_encodes_when_text_changes() -> None:
    store = _FakeStore()
    encoder = _FakeEncoder()
    log = _CaptureLogger()
    repo = _FakeRepo(rows=[PropertyText(property_id="P1", title="A", description="B")])
    run_embedding_batch(repository=repo, store=store, encoder=encoder, logger=log)
    repo2 = _FakeRepo(rows=[PropertyText(property_id="P1", title="A", description="B-updated")])
    written = run_embedding_batch(repository=repo2, store=store, encoder=encoder, logger=log)
    assert written == 1
