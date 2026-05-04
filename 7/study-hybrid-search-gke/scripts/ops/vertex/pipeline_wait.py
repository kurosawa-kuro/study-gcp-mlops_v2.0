"""Wait for the most recent Vertex Pipeline run to reach SUCCEEDED.

Usage::

    make ops-train-wait

Environment:
    PIPELINE_DISPLAY_NAME   default: ``property-search-train``
    PIPELINE_WAIT_TIMEOUT_SECONDS  default: ``1800``
    PIPELINE_WAIT_POLL_SECONDS     default: ``30``
"""

from __future__ import annotations

import os
import time
from typing import Any

from scripts._common import env, fail, resolve_project_id

TERMINAL_FAILURE_STATES = {"FAILED", "CANCELLED", "CANCELLING", "PAUSED"}


def _state_name(raw_state: object) -> str:
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
    as_int = int(getattr(raw_state, "value", raw_state) or 0)
    return state_names.get(as_int, str(raw_state))


def _latest_job(*, aiplatform: Any, display_name: str) -> Any | None:
    jobs = aiplatform.PipelineJob.list(
        filter=f'display_name="{display_name}"',
        order_by="create_time desc",
    )
    for job in jobs[:20]:
        if getattr(job, "display_name", "") == display_name:
            return job
    return None


def main() -> int:
    project_id = resolve_project_id()
    region = env("VERTEX_LOCATION", env("REGION", "asia-northeast1"))
    display_name = os.environ.get("PIPELINE_DISPLAY_NAME", "property-search-train")
    timeout_seconds = int(os.environ.get("PIPELINE_WAIT_TIMEOUT_SECONDS", "1800"))
    poll_seconds = int(os.environ.get("PIPELINE_WAIT_POLL_SECONDS", "30"))
    if not project_id:
        return fail(
            "vertex-pipeline-wait: missing GCP_PROJECT (Composer injects). "
            "Fix Terraform Composer env — do not patch env/config/setting.yaml for live."
        )

    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=region)
    deadline = time.monotonic() + timeout_seconds
    last_state = ""
    while time.monotonic() < deadline:
        job = _latest_job(aiplatform=aiplatform, display_name=display_name)
        if job is None:
            return fail(
                f"vertex-pipeline-wait: no PipelineJob found with display_name={display_name!r}"
            )
        state = _state_name(getattr(job, "state", None))
        resource_name = str(getattr(job, "resource_name", "") or getattr(job, "name", "-"))
        if state != last_state:
            print(f"vertex-pipeline-wait: state={state} job={resource_name}")
            last_state = state
        if state == "SUCCEEDED":
            print(f"vertex-pipeline-wait PASS: {resource_name}")
            return 0
        if state in TERMINAL_FAILURE_STATES:
            return fail(f"vertex-pipeline-wait: latest run ended in state={state}: {resource_name}")
        time.sleep(poll_seconds)

    return fail(
        "vertex-pipeline-wait: timed out waiting for latest run to finish "
        f"(display_name={display_name!r}, timeout_seconds={timeout_seconds})"
    )


if __name__ == "__main__":
    raise SystemExit(main())
