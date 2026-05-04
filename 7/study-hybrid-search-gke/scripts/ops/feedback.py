"""/search → take request_id + first property_id → POST /feedback (click).
Verifies the publisher → Pub/Sub → BQ Subscription path works end to end.
"""

from __future__ import annotations

import json
import os

from scripts._common import fail, print_pretty, resolve_api_target


def main() -> int:
    query = os.environ.get("QUERY", "品川駅")
    action = os.environ.get("ACTION", "click")

    try:
        target = resolve_api_target()
    except Exception as exc:
        return fail(f"feedback config error: {exc}")

    status, body = target.call("POST", "/search", payload={"query": query, "top_k": 1})
    if status != 200:
        return fail(f"search returned HTTP {status}: {body}")

    data = json.loads(body)
    request_id = data.get("request_id")
    results = data.get("results") or []
    property_id = results[0].get("property_id") if results else None
    if not request_id or not property_id:
        return fail(
            f"feedback-check failed: empty request_id or property_id\nsearch response: {body}"
        )

    fb_status, fb_body = target.call(
        "POST",
        "/feedback",
        payload={"request_id": request_id, "property_id": property_id, "action": action},
    )
    if fb_status != 200:
        return fail(f"feedback returned HTTP {fb_status}: {fb_body}")
    print_pretty(fb_body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
