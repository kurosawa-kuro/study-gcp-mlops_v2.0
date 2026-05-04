"""Register the latest train-reranker output into Vertex Model Registry.

Phase 5 回避策: Vertex Pipelines 内で `packages_to_install=google-cloud-aiplatform`
を付けた `register-reranker` component の worker が起動直後に exit 1 する事象が
再現する (ログすら出ない)。pipeline 側は minimal stub のまま SUCCEED させ、
Model Registry への upload はこのローカルスクリプトで実施する。

Usage:
  uv run python -m scripts.ops.register_model
  uv run python -m scripts.ops.register_model --apply
  uv run python -m scripts.ops.register_model --pipeline-job-id property-search-train-20260423172541 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from scripts._common import env


def _latest_pipeline_run(project_id: str, location: str, display_name: str) -> str:
    """Resource name of the most recent SUCCEEDED PipelineJob."""
    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=location)
    jobs = aiplatform.PipelineJob.list(
        filter=f'display_name="{display_name}"',
        order_by="create_time desc",
    )
    for j in jobs[:20]:
        state = getattr(j, "state", None)
        if state and "SUCCEEDED" in str(state):
            return str(j.resource_name)
    raise RuntimeError(f"No SUCCEEDED pipeline found with display_name={display_name}")


def _resolve_model_uri_from_gcs(*, project_id: str, pipeline_resource_name: str) -> str:
    """Walk pipeline-root bucket and find train-reranker's executor_output.json."""
    import google.cloud.storage as gcs_storage
    from google.cloud import aiplatform

    # GCS path uses the numeric project number (not project_id). Fetch it from
    # the pipeline resource name if available, otherwise resolve via aiplatform.
    parts = pipeline_resource_name.split("/")
    maybe_num = parts[1] if len(parts) >= 2 else ""
    if maybe_num.isdigit():
        project_num = maybe_num
    else:
        aiplatform.init(project=project_id)
        # Walk resource tree to resolve PROJECT_NUMBER: fetch the job, which
        # returns the numeric form in .resource_name
        aiplatform.init(project=project_id)
        job = aiplatform.PipelineJob.get(pipeline_resource_name)
        numeric = job.resource_name.split("/")[1]
        project_num = numeric
    pipeline_job_name = parts[-1]
    bucket_name = f"{project_id}-pipeline-root"
    base = f"runs/{project_num}/{pipeline_job_name}/"

    client = gcs_storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    for blob in bucket.list_blobs(prefix=base):
        if not blob.name.startswith(base + "train-reranker_"):
            continue
        if not blob.name.endswith("/executor_output.json"):
            continue
        body = blob.download_as_bytes()
        payload = json.loads(body)
        # KFP v2 executor output shape
        artifacts_block = payload.get("artifacts", {}).get("model", {})
        if isinstance(artifacts_block, dict):
            artifacts = artifacts_block.get("artifacts", [])
            if isinstance(artifacts, list) and artifacts:
                uri = str(artifacts[0].get("uri", ""))
                if uri:
                    return uri
        # Fallback: read "Output" string return value
        params = payload.get("parameterValues") or payload.get("parameters") or {}
        if isinstance(params, dict) and "Output" in params:
            raw = params["Output"]
            if isinstance(raw, dict):
                uri = str(raw.get("stringValue") or raw.get("string_value") or "")
                if uri:
                    return uri
            elif isinstance(raw, str) and raw:
                return raw
    raise RuntimeError(f"could not locate train-reranker output under gs://{bucket_name}/{base}")


def _upload_model(
    *,
    project_id: str,
    location: str,
    display_name: str,
    artifact_dir_uri: str,
    serving_container_image_uri: str,
) -> dict[str, Any]:
    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=location)
    print(f"[register_model] uploading artifact_dir_uri={artifact_dir_uri}")
    print(f"[register_model] serving_container_image_uri={serving_container_image_uri}")
    uploaded = aiplatform.Model.upload(
        display_name=display_name,
        artifact_uri=artifact_dir_uri,
        serving_container_image_uri=serving_container_image_uri,
        serving_container_predict_route="/predict",
        serving_container_health_route="/health",
        serving_container_ports=[8080],
        version_aliases=["staging"],
        sync=True,
    )
    return {
        "resource_name": uploaded.resource_name,
        "version_id": uploaded.version_id,
        "artifact_uri": artifact_dir_uri,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Register the latest train-reranker output to Vertex Model Registry"
    )
    parser.add_argument(
        "--pipeline-display-name",
        default="property-search-train",
        help="Pipeline display name to locate the most recent SUCCEEDED run",
    )
    parser.add_argument(
        "--pipeline-job-id",
        default=None,
        help="Explicit pipeline job id (e.g. property-search-train-20260423172541). "
        "Overrides --pipeline-display-name lookup.",
    )
    parser.add_argument(
        "--model-display-name",
        default="property-reranker",
    )
    parser.add_argument(
        "--serving-container-image-uri",
        default=None,
        help="Overrides default property-reranker:latest image URI",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    project_id = env("PROJECT_ID") or "mlops-dev-a"
    location = env("VERTEX_LOCATION", env("REGION")) or "asia-northeast1"
    repo = env("ARTIFACT_REPO", "mlops") or "mlops"
    serving_image = (
        args.serving_container_image_uri
        or f"{location}-docker.pkg.dev/{project_id}/{repo}/property-reranker:latest"
    )

    if args.pipeline_job_id:
        pipeline_resource_name = (
            f"projects/{project_id}/locations/{location}/pipelineJobs/{args.pipeline_job_id}"
        )
    else:
        pipeline_resource_name = _latest_pipeline_run(
            project_id, location, args.pipeline_display_name
        )
    print(f"[register_model] pipeline_resource_name={pipeline_resource_name}")

    model_uri = _resolve_model_uri_from_gcs(
        project_id=project_id, pipeline_resource_name=pipeline_resource_name
    )
    print(f"[register_model] model_uri={model_uri}")

    # Vertex Model.upload expects a DIRECTORY prefix, not an OBJECT URI.
    artifact_dir_uri = model_uri.rsplit("/", 1)[0] + "/" if "/" in model_uri else model_uri
    print(f"[register_model] artifact_dir_uri={artifact_dir_uri}")
    print(f"[register_model] model_display_name={args.model_display_name}")
    print(f"[register_model] serving_container_image_uri={serving_image}")

    if not args.apply:
        print("[register_model] dry-run: pass --apply to actually upload")
        return 0

    result = _upload_model(
        project_id=project_id,
        location=location,
        display_name=args.model_display_name,
        artifact_dir_uri=artifact_dir_uri,
        serving_container_image_uri=serving_image,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
