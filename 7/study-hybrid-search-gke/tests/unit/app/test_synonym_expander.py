"""Phase 7 SYN-1 — RedisSynonymExpander unit tests (in-memory fake Redis).

Mirrors the Phase 3 tests at ``3/study-hybrid-search-local/tests/unit/app/
test_synonym_expander.py``. Both phases share the same Port shape and
the same adapter wire format (``syn:<token>`` SET → SMEMBERS), so the
tests are intentionally identical except for the import paths.

Covers the Port contract:

- ``NoopSynonymExpander`` returns the query verbatim
- HIT path: tokens are expanded with their synonyms, original tokens
  preserved at the head
- MISS path (token unknown): query unchanged
- Backend failure: ``expand`` swallows exceptions and falls back to the
  original query (``/search`` availability cannot depend on Redis)
- ``max_synonyms_per_token`` truncates runaway entries
- Cross-token deduplication: a synonym shared between two input tokens
  appears at most once
- Decoded-string clients (``decode_responses=True``) are accepted

These tests use only an in-memory fake; they do not require a running
Redis instance and run inside ``make check`` / ``make test``.
"""

from __future__ import annotations

from typing import Any

from app.services.adapters.redis_synonym_expander import RedisSynonymExpander
from app.services.noop_adapters.noop_synonym_expander import NoopSynonymExpander


def _b(*texts: str) -> set[bytes]:
    """Helper — string set → bytes set (avoids UP012 noise on non-ASCII literals)."""
    return {bytes(t, "utf-8") for t in texts}


class _FakeRedis:
    """Minimal stand-in for ``redis.Redis`` returning bytes (matches the
    real client's default ``decode_responses=False`` behaviour)."""

    def __init__(self, dictionary: dict[str, set[bytes]]) -> None:
        self._d = dictionary

    def smembers(self, key: str) -> set[bytes]:
        return self._d.get(key, set())


class _FlakyRedis:
    """Fake that raises on every call — exercises the swallow-and-fallback path."""

    def smembers(self, key: str) -> set[bytes]:
        raise ConnectionError("simulated outage")


def test_noop_returns_query_unchanged() -> None:
    assert NoopSynonymExpander().expand("駅近 2LDK") == "駅近 2LDK"
    assert NoopSynonymExpander().expand("") == ""


def test_redis_expands_known_tokens_with_synonyms() -> None:
    fake = _FakeRedis(
        {
            "syn:駅近": _b("駅徒歩", "アクセス良好"),
            "syn:2LDK": _b("2DK", "2部屋"),
        }
    )
    expander = RedisSynonymExpander(client=fake)
    expanded = expander.expand("駅近 2LDK")
    tokens = expanded.split()
    # original tokens preserved at the head
    assert tokens[0] == "駅近"
    assert tokens[1] in {"アクセス良好", "駅徒歩"}
    assert "2LDK" in tokens
    assert "2DK" in tokens
    assert "2部屋" in tokens
    # no duplicates
    assert len(tokens) == len(set(tokens))


def test_redis_keeps_query_when_no_synonyms_known() -> None:
    fake = _FakeRedis({})
    assert RedisSynonymExpander(client=fake).expand("白金台 戸建") == "白金台 戸建"


def test_redis_returns_original_on_backend_failure() -> None:
    expander = RedisSynonymExpander(client=_FlakyRedis())
    # backend raises, but expand() must still return the original query.
    assert expander.expand("駅近 2LDK") == "駅近 2LDK"


def test_redis_caps_synonyms_per_token() -> None:
    many = _b(*(f"alt-{i}" for i in range(20)))
    fake = _FakeRedis({"syn:駅近": many})
    expander = RedisSynonymExpander(client=fake, max_synonyms_per_token=3)
    expanded = expander.expand("駅近")
    tokens = expanded.split()
    assert tokens[0] == "駅近"
    # at most 3 synonyms appended → 4 total tokens
    assert len(tokens) == 4


def test_redis_dedupes_across_tokens() -> None:
    # Two tokens share the synonym "共同住宅" — it must appear at most once.
    fake = _FakeRedis(
        {
            "syn:マンション": _b("共同住宅", "アパート"),
            "syn:アパート": _b("共同住宅", "マンション"),
        }
    )
    expander = RedisSynonymExpander(client=fake)
    expanded = expander.expand("マンション アパート")
    tokens = expanded.split()
    assert tokens.count("共同住宅") == 1
    assert tokens.count("マンション") == 1
    assert tokens.count("アパート") == 1


def test_redis_handles_string_decoded_values() -> None:
    """``decode_responses=True`` clients return str directly — adapter must accept both."""

    class _StrRedis:
        def smembers(self, key: str) -> set[Any]:
            return {"駅徒歩"} if key == "syn:駅近" else set()

    expander = RedisSynonymExpander(client=_StrRedis())
    assert "駅徒歩" in expander.expand("駅近").split()
