"""Redis-backed ``/search`` response cache.

Implements ``SearchCachePort`` against the Phase 3 Docker Compose Redis
instance (also serving the synonym dictionary; the namespaces do not
collide because key prefixes are distinct: ``syn:*`` vs ``search:v1:*``).

Wire shape:

    SETEX search:v1:{sha256(spec)[:32]} <ttl> <json bytes>
    GET   search:v1:{sha256(spec)[:32]}            → bytes | None

The hash payload is deterministic JSON over a stable spec dict so the
key is invariant under ``filters`` key insertion order:

    {
      "v": "v1",
      "q": "<query>",
      "f": [["layout", "2LDK"], ["max_rent", 150000]],   # sorted
      "k": 10,
      "e": false
    }

Failures (network errors, decode errors, missing libraries) silently fall
back: ``get`` returns ``None`` (caller does live search) and ``set``
becomes a noop (next call MISSes again). The cache is intentionally
best-effort because /search availability cannot depend on Redis.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from typing import Any

from app.domain.candidate import Candidate, RankedCandidate
from app.domain.search import SearchInput, SearchOutput, SearchResultItem
from app.services.protocols.search_cache import SearchCachePort

logger = logging.getLogger("app.services.adapters.redis_search_cache")


class RedisSearchCache(SearchCachePort):
    """Phase 3 adapter — talks to the Docker Compose Redis container."""

    KEY_VERSION = "v1"

    def __init__(
        self,
        *,
        client: Any,
        ttl_seconds: int,
        key_prefix: str = "search:",
    ) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._prefix = key_prefix

    def get(self, request: SearchInput) -> SearchOutput | None:
        try:
            raw = self._client.get(self._key(request))
        except Exception:
            logger.exception("RedisSearchCache.get failed; falling back to live search")
            return None
        if raw is None:
            return None
        try:
            return self._deserialize(raw)
        except Exception:
            logger.exception(
                "RedisSearchCache: failed to deserialize cached entry; treating as MISS"
            )
            return None

    def set(self, request: SearchInput, output: SearchOutput) -> None:
        try:
            payload = json.dumps(self._serialize(output), ensure_ascii=False)
            self._client.setex(self._key(request), self._ttl, payload)
        except Exception:
            logger.exception("RedisSearchCache.set failed; next request will MISS and re-execute")

    # ------------------------------------------------------------------ internals

    def _key(self, request: SearchInput) -> str:
        spec = {
            "v": self.KEY_VERSION,
            "q": request.query,
            "f": sorted(dict(request.filters).items()),
            "k": request.top_k,
            "e": bool(request.explain),
        }
        raw = json.dumps(spec, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"{self._prefix}{self.KEY_VERSION}:{digest}"

    def _serialize(self, output: SearchOutput) -> dict[str, Any]:
        # ``ranked`` is intentionally dropped — see Port docstring.
        # ``request_id`` is also dropped — callers stamp their own when
        # returning a HIT so downstream tracking still sees distinct
        # request IDs per actual incoming HTTP call.
        return {
            "items": [asdict(item) for item in output.items],
            "model_path": output.model_path,
        }

    def _deserialize(self, raw: bytes | str) -> SearchOutput:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        items = [_item_from_dict(d) for d in payload.get("items", [])]
        return SearchOutput(
            request_id="",  # caller overrides with the live request_id on HIT
            items=items,
            model_path=payload.get("model_path"),
            ranked=_ranked_from_items(items),
        )


def _item_from_dict(d: dict[str, Any]) -> SearchResultItem:
    """Defensive reconstruction — only known keys are read.

    SearchResultItem is a frozen dataclass with many optional display
    fields. New fields added in the future won't crash the deserialiser
    when an old cache entry is read; old fields removed will surface as
    ``KeyError`` here, which the outer ``except`` swallows so the cache
    entry is treated as MISS.
    """
    return SearchResultItem(
        property_id=d["property_id"],
        final_rank=d["final_rank"],
        lexical_rank=d["lexical_rank"],
        semantic_rank=d["semantic_rank"],
        me5_score=d["me5_score"],
        score=d.get("score"),
        attributions=d.get("attributions"),
        popularity_score=d.get("popularity_score"),
        title=d.get("title"),
        city=d.get("city"),
        ward=d.get("ward"),
        layout=d.get("layout"),
        rent=d.get("rent"),
        walk_min=d.get("walk_min"),
        age_years=d.get("age_years"),
        area_m2=d.get("area_m2"),
        pet_ok=d.get("pet_ok"),
    )


def _ranked_from_items(items: list[SearchResultItem]) -> list[RankedCandidate]:
    """Reconstruct a minimal ``ranked`` list so ``SearchOutput`` stays type-clean.

    On cache HIT the reconstituted ``RankedCandidate`` carries the cached
    ranking metadata (``lexical_rank``, ``semantic_rank``, ``me5_score``)
    but ``property_features`` is empty — by design. ``ranked`` is only
    used by ``ranking_log_publisher`` which the SearchService skips on
    HIT (the original MISS already published the row).
    """
    out: list[RankedCandidate] = []
    for item in items:
        candidate = Candidate(
            property_id=item.property_id,
            lexical_rank=item.lexical_rank,
            semantic_rank=item.semantic_rank,
            me5_score=item.me5_score,
            property_features={},
        )
        out.append(
            RankedCandidate(
                candidate=candidate,
                final_rank=item.final_rank,
                score=item.score,
                attributions=item.attributions,
            )
        )
    return out
