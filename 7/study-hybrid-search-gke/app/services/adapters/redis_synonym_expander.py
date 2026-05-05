"""Redis-backed synonym dictionary for lexical query expansion.

Implements ``SynonymExpanderPort`` against a Redis SET-of-synonyms layout:

    syn:マンション → {"アパート", "共同住宅", "集合住宅"}
    syn:駅近        → {"駅徒歩", "駅から徒歩", "アクセス良好"}
    syn:2LDK        → {"2DK", "2部屋"}

Lookup strategy:

1. Tokenize ``query`` on whitespace. CJK characters stay grouped — the
   downstream Meilisearch BM25 applies its own tokenizer.
2. For each token ``t`` fetch ``SMEMBERS syn:{t}``.
3. Concatenate the original tokens plus all unique synonym members,
   joined with single spaces.

Failures (connection errors, decoding errors, missing keys) silently
fall back to returning the original query — query expansion is a
best-effort lexical recall booster, not load-bearing for /search
correctness.
"""

from __future__ import annotations

from typing import Any

from app.services.protocols.synonym_expander import SynonymExpanderPort
from ml.common.logging import get_logger

logger = get_logger("app.services.adapters.redis_synonym_expander")


class RedisSynonymExpander(SynonymExpanderPort):
    """Phase 7 production adapter — talks to Cloud Memorystore for Redis.

    Constructed once at startup with a connected ``redis.Redis`` client.
    Each ``expand`` call performs ``len(tokens)`` ``SMEMBERS`` calls.
    For modest dictionaries (~10⁴ entries) and short queries the cost is
    sub-millisecond, dominated by RTT to the Memorystore primary.
    """

    DEFAULT_KEY_PREFIX = "syn:"

    def __init__(
        self,
        *,
        client: Any,
        key_prefix: str | None = None,
        max_synonyms_per_token: int = 8,
    ) -> None:
        self._client = client
        self._prefix = key_prefix if key_prefix is not None else self.DEFAULT_KEY_PREFIX
        self._max_synonyms_per_token = max_synonyms_per_token

    def expand(self, query: str) -> str:
        tokens = query.split()
        if not tokens:
            return query
        try:
            return self._expand_tokens(tokens)
        except Exception:
            logger.exception("RedisSynonymExpander failed; using original query")
            return query

    def _expand_tokens(self, tokens: list[str]) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for tok in tokens:
            if tok and tok not in seen:
                out.append(tok)
                seen.add(tok)
            members = self._client.smembers(f"{self._prefix}{tok}")
            decoded = [m for m in (_decode(raw) for raw in members) if m]
            decoded.sort()
            for syn in decoded[: self._max_synonyms_per_token]:
                if syn not in seen:
                    out.append(syn)
                    seen.add(syn)
        return " ".join(out)


def _decode(raw: object) -> str:
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    if isinstance(raw, str):
        return raw
    return ""
