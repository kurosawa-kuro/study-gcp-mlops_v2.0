"""Hit /livez on the deployed search-api. /healthz is reserved by Cloud Run's
Knative frontend (returns its own HTML 404 before reaching the container),
so we use the /livez alias registered in app/src/app/entrypoints/api.py.
"""

from __future__ import annotations

from scripts._common import fail, resolve_api_target


def main() -> int:
    try:
        target = resolve_api_target()
    except Exception as exc:
        return fail(f"livez config error: {exc}")
    status, body = target.call("GET", "/livez")
    if status != 200:
        return fail(f"livez returned HTTP {status}: {body}")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
