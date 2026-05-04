"""Generate a small batch of feedback events (click / favorite / inquiry)
against the deployed /search → /feedback path. Use to bootstrap training-side
label distribution before the first real users arrive.

Repeats up to N_PER_ACTION times per action and posts whichever search call
yields a property_id first.
"""

from __future__ import annotations

import json
import os
import time

from scripts._common import fail, resolve_api_target

ACTIONS = ("click", "favorite", "inquiry")


def main() -> int:
    query = os.environ.get("QUERY", "札幌 ペット可 2LDK")
    n_per_action = int(os.environ.get("N_PER_ACTION", "5"))

    try:
        target = resolve_api_target()
    except Exception as exc:
        return fail(f"label-seed config error: {exc}")
    search_payload = {"query": query, "top_k": 5}

    posted = 0
    for action in ACTIONS:
        for _ in range(n_per_action):
            status, body = target.call("POST", "/search", payload=search_payload)
            if status != 200:
                time.sleep(1)
                continue
            data = json.loads(body)
            rid = data.get("request_id")
            results = data.get("results") or []
            pid = results[0].get("property_id") if results else None
            if rid and pid:
                target.call(
                    "POST",
                    "/feedback",
                    payload={"request_id": rid, "property_id": pid, "action": action},
                )
                posted += 1
                print(f"posted action={action} property_id={pid} request_id={rid}")
                break
            time.sleep(1)

    print(f"label-seed completed: posted={posted}")
    if posted == 0:
        return fail("label-seed failed: no feedback posted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
