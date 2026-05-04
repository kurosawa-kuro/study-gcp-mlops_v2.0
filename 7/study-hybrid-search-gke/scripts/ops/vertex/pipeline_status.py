"""List recent Vertex AI Pipelines runs and their state.

Verifies the train + embed pipelines actually succeeded recently (for
``train_pipeline`` and ``embed_pipeline``). Useful before a deploy to
confirm the ``production`` alias was promoted off a real, finished run
and not a smoke-mode fixture.

Usage::

    make ops-vertex-pipeline-status [LIMIT=10]

Exit codes:
    0  — at least one SUCCEEDED run for any pipeline
    1  — no SUCCEEDED run in the listed window (or config error)
"""

from __future__ import annotations

import os

from scripts._common import env, fail


def main() -> int:
    project_id = env("PROJECT_ID")
    region = env("VERTEX_LOCATION", env("REGION", "asia-northeast1"))
    limit = int(os.environ.get("LIMIT", "10"))
    if not project_id:
        return fail("vertex-pipeline-status: PROJECT_ID is required")

    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=region)

    try:
        runs = aiplatform.PipelineJob.list(order_by="create_time desc")
    except Exception as exc:
        return fail(f"vertex-pipeline-status: list error: {exc}")

    # PipelineState enum values per
    # https://cloud.google.com/vertex-ai/docs/reference/rest/v1/PipelineState.
    state_names: dict[int, str] = {
        0: "UNSPECIFIED",
        1: "QUEUED",
        2: "PENDING",
        3: "RUNNING",
        4: "SUCCEEDED",
        5: "FAILED",
        6: "CANCELLING",
        7: "CANCELLED",
        8: "PAUSED",
    }

    succeeded = 0
    print(f"latest {limit} pipeline runs in {project_id}/{region}:")
    for j in list(runs)[:limit]:
        raw_state = getattr(j, "state", None)
        # SDK exposes the enum either as IntEnum (.value) or plain int.
        as_int = int(getattr(raw_state, "value", raw_state) or 0)
        state = state_names.get(as_int, str(raw_state))
        name = getattr(j, "display_name", "-")
        ct = str(getattr(j, "create_time", "-"))
        if state == "SUCCEEDED":
            succeeded += 1
        print(f"  [{state:<12}] {name:<40} created={ct}")

    if succeeded == 0:
        return fail(
            f"vertex-pipeline-status: 0 SUCCEEDED runs in last {limit} — "
            f"run `make ops-train-now` or `embed` before relying on production aliases",
            code=1,
        )
    print(f"\nSUCCEEDED in window: {succeeded}/{limit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
