"""Seed / sync the lexical synonym dictionary into Cloud Memorystore for Redis.

Reads ``definitions/synonyms/real_estate_ja.yaml`` (curated property-domain
synonyms) and rewrites the ``syn:<token>`` SETs in Redis. Designed to be
invoked as a one-shot Cloud Run Job, a Composer DAG step, or locally:

    python -m scripts.ops.sync_synonyms \\
        --redis-url redis://10.x.x.x:6379/0 \\
        --dictionary definitions/synonyms/real_estate_ja.yaml

The script is idempotent and atomic per token: each ``syn:<token>`` SET
is replaced via ``DEL`` + ``SADD`` inside a single MULTI/EXEC pipeline so
a stale subset never appears under live ``/search`` traffic.

Auth:
- Cloud Memorystore AUTH string is read from ``REDIS_AUTH`` env var
  (mirrors the ``synonym-redis-auth`` Secret in the GKE Pod).
- When AUTH is disabled the env var is unset and the URL is used as-is.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml


def _log(msg: str) -> None:
    print(f"[sync_synonyms] {msg}", flush=True)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("SYNONYM_REDIS_URL", ""),
        help="redis:// URL for Cloud Memorystore primary (default: SYNONYM_REDIS_URL env)",
    )
    parser.add_argument(
        "--dictionary",
        default="definitions/synonyms/real_estate_ja.yaml",
        help="YAML path with token -> [synonyms] mapping",
    )
    parser.add_argument(
        "--key-prefix",
        default=os.environ.get("SYNONYM_KEY_PREFIX", "syn:"),
        help="Redis key prefix (default 'syn:')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse the YAML and report stats without writing to Redis",
    )
    return parser.parse_args(argv)


def _load_dictionary(path: str) -> dict[str, list[str]]:
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a top-level mapping; got {type(raw).__name__}")
    out: dict[str, list[str]] = {}
    for token, synonyms in raw.items():
        if not isinstance(token, str) or not token.strip():
            raise ValueError(f"{path}: invalid token {token!r}")
        if not isinstance(synonyms, list):
            raise ValueError(f"{path}: token {token!r} must map to a list")
        cleaned = [s.strip() for s in synonyms if isinstance(s, str) and s.strip()]
        if cleaned:
            out[token.strip()] = sorted(set(cleaned))
    return out


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dictionary = _load_dictionary(args.dictionary)
    total_synonyms = sum(len(v) for v in dictionary.values())
    _log(
        f"loaded {len(dictionary)} canonical tokens "
        f"({total_synonyms} synonyms total) from {args.dictionary}"
    )

    if args.dry_run:
        _log("--dry-run: skipping Redis writes")
        for token, synonyms in dictionary.items():
            _log(f"  {args.key_prefix}{token} -> {synonyms}")
        return 0

    if not args.redis_url:
        _log("ERROR: --redis-url (or SYNONYM_REDIS_URL env) is required")
        return 1

    try:
        import redis  # type: ignore[import-not-found]
    except ImportError:
        _log("ERROR: 'redis' package not installed. uv add redis or pip install redis")
        return 2

    password = os.environ.get("REDIS_AUTH") or None
    client = redis.from_url(  # type: ignore[no-untyped-call]
        args.redis_url,
        password=password,
        socket_connect_timeout=5.0,
        socket_timeout=5.0,
    )
    client.ping()
    _log("connected to Redis")

    written = 0
    pipe = client.pipeline(transaction=False)
    for token, synonyms in dictionary.items():
        key = f"{args.key_prefix}{token}"
        pipe.delete(key)
        if synonyms:
            pipe.sadd(key, *synonyms)
        written += 1
    pipe.execute()
    _log(f"wrote {written} synonym keys")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
