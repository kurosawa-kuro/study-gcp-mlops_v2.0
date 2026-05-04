"""Verify the Phase 6 T4 Explainable AI path: ``/search?explain=true``.

The reranker's ``predict_with_explain`` should return per-feature
attributions for each candidate. This script asserts at least one
result row has a non-empty ``attributions`` dict, which proves the
KServe reranker received the explain flag end-to-end and the adapter
path is wired.

Usage::

    QUERY="新宿 1LDK" make ops-vertex-explain

Exit codes:
    0  — at least one row with attributions present
    1  — non-200 or all rows have empty attributions (path broken)
"""

from __future__ import annotations

import json
import os

from scripts._common import fail, resolve_api_target


def main() -> int:
    query = os.environ.get("QUERY", "新宿区西新宿 1LDK")
    top_k = int(os.environ.get("TOP_K", "5"))

    try:
        target = resolve_api_target()
    except Exception as exc:
        return fail(f"vertex-explain: config error: {exc}")

    payload = {"query": query, "filters": {"max_rent": 200000}, "top_k": top_k}
    status, body = target.call("POST", "/search?explain=true", payload=payload)
    if status != 200:
        return fail(f"vertex-explain: HTTP {status}: {body[:300]}")

    data = json.loads(body)
    rows = data.get("results") or []
    with_attrs = [r for r in rows if r.get("attributions")]

    print(f"vertex-explain: rows={len(rows)} with_attributions={len(with_attrs)}")
    for r in with_attrs[:3]:
        print(f"  pid={r.get('property_id')} attributions={r.get('attributions')}")

    if not with_attrs:
        return fail(
            "vertex-explain: zero rows have attributions. "
            "Check reranker_client.predict_with_explain wiring and "
            "KServe explain endpoint URL config."
        )
    print("vertex-explain PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
