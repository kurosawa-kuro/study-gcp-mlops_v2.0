"""Smoke-test the deployed /search endpoint. Phase 4 (rerank-free) returns
results where final_rank == lexical_rank and score is null.
Override QUERY / TOP_K / MAX_RENT via env vars.
"""

from __future__ import annotations

import os
import time
from urllib.error import URLError

from scripts._common import fail, print_pretty, resolve_api_target


def _search_once(*, payload: dict[str, object]) -> tuple[int, str]:
    target = resolve_api_target()
    return target.call("POST", "/search", payload=payload)


def main() -> int:
    query = os.environ.get("QUERY", "赤羽駅徒歩10分 ペット可")
    top_k = int(os.environ.get("TOP_K", "20"))
    max_rent = int(os.environ.get("MAX_RENT", "150000"))
    retries = int(os.environ.get("SEARCH_RETRIES", "3"))
    retry_sleep = float(os.environ.get("SEARCH_RETRY_SLEEP", "2.0"))

    payload = {"query": query, "filters": {"max_rent": max_rent}, "top_k": top_k}
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            status, body = _search_once(payload=payload)
            break
        except (TimeoutError, URLError, OSError) as exc:
            last_exc = exc
            if attempt >= retries:
                return fail(
                    f"search timed out after {retries} attempt(s): {exc}. "
                    "check search-api / gateway logs if this is persistent."
                )
            print(
                f"[ops-search] transient failure attempt={attempt}/{retries}: {exc} "
                f"(sleep {retry_sleep:.1f}s, retrying)",
                flush=True,
            )
            time.sleep(retry_sleep)
        except Exception as exc:
            return fail(f"search config error: {exc}")
    else:
        if last_exc is not None:
            return fail(f"search failed: {last_exc}")
        return fail("search failed without a response")

    if status != 200:
        return fail(f"search returned HTTP {status}: {body}")
    print_pretty(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
