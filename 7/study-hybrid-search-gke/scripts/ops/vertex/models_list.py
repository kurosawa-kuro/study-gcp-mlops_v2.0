"""List Vertex AI Model Registry entries for property-encoder / property-reranker.

Verifies the prerequisites of ``make deploy-kserve-models`` (which expects a
``production`` alias on each Model). Surfaces per-version artifact_uri so
mismatches with the actual GCS object location (the Run 1 reranker/v1 vs
lgbm/v1 incident) become visible at audit time, not at Pod-init time.

Usage::

    make ops-vertex-models-list

Exit codes:
    0  — both models exist with at least one version each
    1  — config error or no versions found
"""

from __future__ import annotations

from scripts._common import env, fail
from scripts.lib.gcp_resources import VERTEX_MODEL_NAMES


def main() -> int:
    project_id = env("PROJECT_ID")
    region = env("VERTEX_LOCATION", env("REGION", "asia-northeast1"))
    if not project_id:
        return fail("vertex-models-list: PROJECT_ID is required")

    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=region)

    overall_ok = True
    for display_name in VERTEX_MODEL_NAMES:
        try:
            models = aiplatform.Model.list(filter=f'display_name="{display_name}"')
        except Exception as exc:
            print(f"[FAIL] {display_name}: list error: {exc}")
            overall_ok = False
            continue

        versions = []
        for m in models:
            # resource_name: projects/.../locations/.../models/<model_id>
            resource_name = getattr(m, "resource_name", "") or ""
            model_id = resource_name.rsplit("/", 1)[-1] if resource_name else "-"
            versions.append(
                {
                    "model_id": model_id,
                    "version_id": getattr(m, "version_id", "-"),
                    "aliases": list(getattr(m, "version_aliases", []) or []),
                    "artifact_uri": getattr(m, "uri", "") or "<empty>",
                    "create_time": str(getattr(m, "create_time", "-")),
                }
            )

        if not versions:
            print(f"[FAIL] {display_name}: no versions registered")
            overall_ok = False
            continue

        prod = [v for v in versions if "production" in v["aliases"]]
        gate = "OK" if prod else "WARN"
        print(
            f"[{gate}] {display_name}: {len(versions)} version(s); production_alias={'yes' if prod else 'NO'}"
        )
        for v in versions:
            aliases_str = ",".join(v["aliases"]) if v["aliases"] else "-"
            print(
                f"    model_id={v['model_id']:<20} "
                f"v{v['version_id']!s:<3} "
                f"aliases={aliases_str:<30} "
                f"uri={v['artifact_uri']:<70} "
                f"created={v['create_time']}"
            )

        if not prod:
            print(
                "    HINT: assign `production` via `make ops-promote-reranker VERSION=v<id> APPLY=1` "
                "(or aiplatform.Model.add_version_aliases) before deploy-kserve-models."
            )

    return 0 if overall_ok else fail("vertex-models-list: gate failed", code=1)


if __name__ == "__main__":
    raise SystemExit(main())
