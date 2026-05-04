"""Gen2 Cloud Function that submits a Vertex AI PipelineJob.

This is intentionally small and env-driven so Terraform can wire it up later
without changing application code. It accepts either an Eventarc CloudEvent
or a direct HTTP-style dict payload when reused in local tooling.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_json_env(name: str) -> dict[str, Any]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{name} must be a JSON object")
    return parsed


def _decode_pubsub_message(event: Mapping[str, Any] | None) -> dict[str, Any]:
    if not event:
        return {}

    data = event.get("data")
    if not isinstance(data, Mapping):
        return {}

    message = data.get("message")
    if not isinstance(message, Mapping):
        return {}

    encoded = message.get("data")
    if not isinstance(encoded, str) or not encoded:
        return {}

    decoded = base64.b64decode(encoded).decode("utf-8")
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise RuntimeError("Pub/Sub payload must decode to a JSON object")
    return payload


def _merge_parameters(event_payload: dict[str, Any]) -> dict[str, Any]:
    parameters = _optional_json_env("PIPELINE_PARAMETER_VALUES")
    event_params = event_payload.get("parameters")
    if isinstance(event_params, dict):
        parameters.update(event_params)
    if "reasons" in event_payload and "retrain_reasons" not in parameters:
        parameters["retrain_reasons"] = event_payload["reasons"]
    return parameters


def _build_job_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{prefix}-{timestamp}-{suffix}"


def trigger_pipeline(
    event: Mapping[str, Any] | None = None, context: Any | None = None
) -> dict[str, Any]:
    del context

    from google.cloud import aiplatform

    project = _env("PROJECT_ID")
    location = _env("VERTEX_LOCATION")
    template_path = _env("PIPELINE_TEMPLATE_URI")
    pipeline_root = _env("PIPELINE_ROOT")
    display_name_prefix = os.getenv("PIPELINE_DISPLAY_NAME_PREFIX", "property-train")
    service_account = os.getenv("PIPELINE_SERVICE_ACCOUNT", "").strip()
    enable_caching = os.getenv("PIPELINE_ENABLE_CACHING", "false").lower() == "true"
    labels = _optional_json_env("PIPELINE_LABELS")
    event_payload = _decode_pubsub_message(event)
    parameter_values = _merge_parameters(event_payload)

    aiplatform.init(project=project, location=location)

    job = aiplatform.PipelineJob(
        display_name=_build_job_id(display_name_prefix),
        template_path=template_path,
        pipeline_root=pipeline_root,
        parameter_values=parameter_values,
        enable_caching=enable_caching,
        labels=labels or None,
    )
    job.submit(service_account=service_account or None)

    return {
        "pipeline_job_resource_name": job.resource_name,
        "template_path": template_path,
        "pipeline_root": pipeline_root,
        "parameter_values": parameter_values,
        "labels": labels,
    }


def submit_pipeline(
    event: Mapping[str, Any] | None = None, context: Any | None = None
) -> dict[str, Any]:
    return trigger_pipeline(event=event, context=context)
