"""Phase 3 SYN-2 — RedisSearchCache unit tests (in-memory fake Redis).

Covers the Port contract:

- HIT path: stored value round-trips through serialise / deserialise
- MISS path: empty backend returns None
- Key stability: same input → same key, different input → different key
- Backend failure: get / set both swallow exceptions and degrade gracefully

The integration of the cache into ``SearchService`` (HIT short-circuit,
MISS write-through) is exercised in ``test_search_service_smoke.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.candidate import Candidate, RankedCandidate
from app.domain.search import SearchInput, SearchOutput, SearchResultItem
from app.services.adapters.redis_search_cache import RedisSearchCache
from app.services.noop_adapters.noop_search_cache import NoopSearchCache


class _FakeRedis:
    """In-memory ``redis.Redis`` stand-in supporting GET / SETEX semantics."""

    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> bytes | None:
        value = self.storage.get(key)
        return value.encode("utf-8") if value is not None else None

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.storage[key] = value
        self.ttls[key] = ttl


class _FlakyRedis:
    """Fake that raises on every call — exercises the swallow-and-fallback path."""

    def get(self, key: str) -> bytes | None:
        raise ConnectionError("simulated outage")

    def setex(self, key: str, ttl: int, value: str) -> None:
        raise ConnectionError("simulated outage")


def _sample_output() -> SearchOutput:
    item = SearchResultItem(
        property_id="prop-001",
        final_rank=1,
        lexical_rank=2,
        semantic_rank=3,
        me5_score=0.42,
        score=0.99,
        title="駅近 2LDK",
        layout="2LDK",
        rent=140_000,
    )
    candidate = Candidate(
        property_id="prop-001",
        lexical_rank=2,
        semantic_rank=3,
        me5_score=0.42,
        property_features={},
    )
    ranked = RankedCandidate(candidate=candidate, final_rank=1, score=0.99)
    return SearchOutput(
        request_id="req-original",
        items=[item],
        model_path="ml/registry/artifacts/latest/model.lgb",
        ranked=[ranked],
    )


def _request(
    *,
    query: str = "駅近 2LDK",
    filters: dict[str, Any] | None = None,
    top_k: int = 10,
    explain: bool = False,
) -> SearchInput:
    return SearchInput(query=query, filters=filters or {}, top_k=top_k, explain=explain)


# ---------------------------------------------------------------- noop adapter


def test_noop_always_misses_and_swallows_writes() -> None:
    cache = NoopSearchCache()
    assert cache.get(_request()) is None
    cache.set(_request(), _sample_output())  # must not raise


# ---------------------------------------------------------------- redis adapter


def test_redis_miss_returns_none() -> None:
    cache = RedisSearchCache(client=_FakeRedis(), ttl_seconds=60)
    assert cache.get(_request()) is None


def test_redis_set_then_get_round_trips_items_and_model_path() -> None:
    fake = _FakeRedis()
    cache = RedisSearchCache(client=fake, ttl_seconds=60)
    request = _request()
    output = _sample_output()
    cache.set(request, output)
    cached = cache.get(request)
    assert cached is not None
    # request_id is intentionally cleared on cache HIT — the SearchService
    # stamps the live request_id when returning to the handler.
    assert cached.request_id == ""
    assert len(cached.items) == 1
    assert cached.items[0].property_id == "prop-001"
    assert cached.items[0].final_rank == 1
    assert cached.items[0].rent == 140_000
    assert cached.model_path == "ml/registry/artifacts/latest/model.lgb"
    # ranked is reconstituted minimally so SearchOutput stays type-clean
    assert len(cached.ranked) == 1
    assert cached.ranked[0].candidate.property_id == "prop-001"
    assert cached.ranked[0].candidate.property_features == {}


def test_redis_writes_use_configured_ttl() -> None:
    fake = _FakeRedis()
    cache = RedisSearchCache(client=fake, ttl_seconds=30)
    cache.set(_request(), _sample_output())
    [(_, ttl)] = fake.ttls.items()
    assert ttl == 30


def test_redis_key_is_stable_under_filter_order() -> None:
    fake = _FakeRedis()
    cache = RedisSearchCache(client=fake, ttl_seconds=60)
    a = _request(filters={"max_rent": 150_000, "layout": "2LDK"})
    b = _request(filters={"layout": "2LDK", "max_rent": 150_000})
    cache.set(a, _sample_output())
    # Same logical request → must HIT regardless of dict insertion order.
    assert cache.get(b) is not None


def test_redis_key_separates_distinct_requests() -> None:
    fake = _FakeRedis()
    cache = RedisSearchCache(client=fake, ttl_seconds=60)
    cache.set(_request(query="駅近"), _sample_output())
    assert cache.get(_request(query="閑静")) is None  # different query
    assert cache.get(_request(top_k=5)) is None  # different top_k
    assert cache.get(_request(filters={"layout": "1K"})) is None  # different filters
    assert cache.get(_request(explain=True)) is None  # different explain flag


def test_redis_get_returns_none_on_backend_failure() -> None:
    cache = RedisSearchCache(client=_FlakyRedis(), ttl_seconds=60)
    assert cache.get(_request()) is None  # must not raise


def test_redis_set_swallows_backend_failure() -> None:
    cache = RedisSearchCache(client=_FlakyRedis(), ttl_seconds=60)
    cache.set(_request(), _sample_output())  # must not raise


def test_redis_get_treats_corrupted_payload_as_miss() -> None:
    fake = _FakeRedis()
    # Manually inject a non-JSON value at a key the adapter would compute.
    cache = RedisSearchCache(client=fake, ttl_seconds=60)
    request = _request()
    fake.storage[cache._key(request)] = "not json"
    assert cache.get(request) is None  # corrupted entry → MISS, no raise


def test_redis_key_prefix_is_namespaced() -> None:
    """Synonym dict (`syn:*`) and search cache (`search:*`) must not collide."""
    fake = _FakeRedis()
    cache = RedisSearchCache(client=fake, ttl_seconds=60, key_prefix="search:")
    cache.set(_request(), _sample_output())
    assert all(k.startswith("search:v1:") for k in fake.storage)


def test_redis_key_prefix_default_excludes_synonym_namespace() -> None:
    """Regression — default prefix must not be ``syn:``."""
    cache = RedisSearchCache(client=_FakeRedis(), ttl_seconds=60)
    key = cache._key(_request())
    assert key.startswith("search:")
    assert not key.startswith("syn:")


# ---------------------------------------------------------------- pytest config


@pytest.fixture(autouse=True)
def _isolate(caplog: pytest.LogCaptureFixture) -> None:
    """The cache adapter logs ``exception`` on backend failure; the test
    suite's default log level can be noisy. Pin to WARNING so traceback
    output stays readable when running ``-q``.
    """
    caplog.set_level("WARNING")
