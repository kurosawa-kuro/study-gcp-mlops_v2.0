"""Strict /search component gate for production-like validation.

This script enforces that a single /search response contains:
- non-empty results
- lexical contribution (lexical_rank < 10000) at least one row
- semantic contribution (semantic_rank < 10000 and me5_score > 0) at least one row
- rerank contribution (score is not null) at least one row
"""

from __future__ import annotations

import json
import os

from scripts._common import fail, print_pretty, resolve_api_target


def _diagnose_semantic_zero(results: list[dict], *, readyz_payload: dict | None) -> str:
    all_semantic_default = all(int(r.get("semantic_rank", 10000)) >= 10000 for r in results)
    all_me5_zero = all(float(r.get("me5_score", 0.0)) <= 0.0 for r in results)
    rerank_enabled = None
    if isinstance(readyz_payload, dict):
        rerank_enabled = readyz_payload.get("rerank_enabled")
    if all_semantic_default and all_me5_zero:
        return (
            "semantic contribution is zero. likely branch: "
            "app.main.search -> encoder is None -> query_vector=[] -> "
            "candidate_retriever retrieves lexical-only and fills defaults "
            "(semantic_rank=10000, me5_score=0.0). "
            f"readyz.rerank_enabled={rerank_enabled}"
        )
    return (
        "semantic contribution is zero. semantic candidates were not observed "
        "in /search results. check encoder endpoint readiness, query/filter suitability, "
        "and feature_mart.property_embeddings coverage."
    )


def main() -> int:
    query = os.environ.get("QUERY", "新宿区西新宿 1LDK")
    top_k = int(os.environ.get("TOP_K", "20"))
    max_rent = int(os.environ.get("MAX_RENT", "150000"))

    try:
        resolved = resolve_api_target()
    except Exception as exc:
        return fail(f"component-check config error: {exc}")

    payload = {"query": query, "filters": {"max_rent": max_rent}, "top_k": top_k}
    status, body = resolved.call("POST", "/search", payload=payload)
    if status != 200:
        return fail(f"component-check search returned HTTP {status}: {body}")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return fail(f"component-check search returned non-JSON body: {body}")

    results = parsed.get("results")
    if not isinstance(results, list) or not results:
        return fail("component-check failed: /search returned empty results")
    typed_results: list[dict] = [r for r in results if isinstance(r, dict)]
    readyz_payload: dict | None = None
    readyz_status, readyz_body = resolved.call("GET", "/readyz")
    if readyz_status == 200:
        try:
            payload_obj = json.loads(readyz_body)
            if isinstance(payload_obj, dict):
                readyz_payload = payload_obj
        except json.JSONDecodeError:
            readyz_payload = None

    lexical_hits = sum(1 for r in typed_results if int(r.get("lexical_rank", 10000)) < 10000)
    semantic_hits = sum(
        1
        for r in typed_results
        if int(r.get("semantic_rank", 10000)) < 10000 and float(r.get("me5_score", 0.0)) > 0.0
    )
    rerank_hits = sum(1 for r in typed_results if r.get("score") is not None)

    print(
        f"[component-check] hits lexical={lexical_hits} semantic={semantic_hits} rerank={rerank_hits} "
        f"readyz_rerank_enabled={None if readyz_payload is None else readyz_payload.get('rerank_enabled')}",
        flush=True,
    )
    print(
        f"[component-check] result sample: "
        f"{[{k: r.get(k) for k in ('property_id', 'lexical_rank', 'semantic_rank', 'me5_score', 'score')} for r in typed_results[:3]]}",
        flush=True,
    )
    if lexical_hits <= 0:
        return fail(
            "component-check failed: lexical contribution is zero "
            "(hint: Meilisearch index may be empty — run the meili sync step and retry)"
        )
    if semantic_hits <= 0:
        reason = _diagnose_semantic_zero(typed_results, readyz_payload=readyz_payload)
        return fail(f"component-check failed: {reason}")
    if rerank_hits <= 0:
        return fail(
            "component-check failed: rerank contribution is zero "
            "(hint: reranker endpoint may be not DEPLOYED or serving a non-LightGBM artifact)"
        )

    print_pretty(body)
    print(
        "component-check passed: "
        f"lexical_hits={lexical_hits} semantic_hits={semantic_hits} rerank_hits={rerank_hits} "
        f"readyz_rerank_enabled={None if readyz_payload is None else readyz_payload.get('rerank_enabled')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
