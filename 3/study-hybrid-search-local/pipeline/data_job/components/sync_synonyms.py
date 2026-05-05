"""Seed / sync the lexical synonym dictionary into the Phase 3 Redis container.

Reads ``definitions/synonyms/real_estate_ja.yaml`` (curated property-domain
synonyms) and rewrites the ``syn:<token>`` SETs in Redis. Designed to be
invoked as a dedicated ``make seed-synonyms`` step locally, or as a sub
step of ``make seed`` for full first-time setup.

The script is idempotent: each ``syn:<token>`` SET is replaced via
``DEL`` + ``SADD`` inside a single non-transactional pipeline so a stale
subset never appears under live ``/search`` traffic.

CLI:

    python -m pipeline.data_job.components.sync_synonyms \\
        --redis-url redis://redis:6379/0 \\
        --dictionary definitions/synonyms/real_estate_ja.yaml
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import redis
import yaml

from ml.common import get_logger

logger = get_logger("pipeline.data_job.sync_synonyms")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        help="redis:// URL (default: REDIS_URL env or redis://redis:6379/0)",
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


def load_dictionary(path: str) -> dict[str, list[str]]:
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


def write_to_redis(
    *,
    client: Any,
    dictionary: dict[str, list[str]],
    key_prefix: str,
) -> int:
    """Replace each ``{key_prefix}{token}`` SET in Redis. Returns key count written."""
    written = 0
    pipe = client.pipeline(transaction=False)
    for token, synonyms in dictionary.items():
        key = f"{key_prefix}{token}"
        pipe.delete(key)
        if synonyms:
            pipe.sadd(key, *synonyms)
        written += 1
    pipe.execute()
    return written


def run(*, redis_url: str, dictionary_path: str, key_prefix: str, dry_run: bool = False) -> int:
    dictionary = load_dictionary(dictionary_path)
    total = sum(len(v) for v in dictionary.values())
    logger.info(
        "loaded %d canonical tokens (%d synonyms total) from %s",
        len(dictionary),
        total,
        dictionary_path,
    )
    if dry_run:
        logger.info("--dry-run: skipping Redis writes")
        return 0
    client = redis.from_url(
        redis_url,
        socket_connect_timeout=5.0,
        socket_timeout=5.0,
    )
    client.ping()
    written = write_to_redis(client=client, dictionary=dictionary, key_prefix=key_prefix)
    logger.info("wrote %d synonym keys to %s", written, redis_url)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return run(
        redis_url=args.redis_url,
        dictionary_path=args.dictionary,
        key_prefix=args.key_prefix,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
