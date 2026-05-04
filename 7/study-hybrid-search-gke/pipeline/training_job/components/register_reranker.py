"""KFP component: upload and optionally deploy a reranker model.

Phase 5 debug: minimized to echo-only to isolate whether the crash is in
pip install / base image / kfp executor, or in the actual Model.upload code.
"""

from kfp import dsl


@dsl.component(
    base_image="python:3.12",
)
def register_reranker(
    project_id: str,
    vertex_location: str,
    model_display_name: str,
    endpoint_resource_name: str,
    serving_container_image_uri: str,
    service_account: str,
    traffic_new_percentage: int,
    deploy_machine_type: str,
    model_artifact_uri: str,
) -> str:
    import sys

    def _log(msg: str) -> None:
        print(f"[register_reranker] {msg}", flush=True)
        print(f"[register_reranker] {msg}", file=sys.stderr, flush=True)

    _log("MINIMAL-REGISTER — entry OK")
    _log(f"  project_id={project_id} model_display_name={model_display_name}")
    _log(f"  model_artifact_uri={model_artifact_uri}")
    _log(f"  serving_container_image_uri={serving_container_image_uri}")
    _log(f"  endpoint_resource_name={endpoint_resource_name!r}")
    _log("MINIMAL-REGISTER — done, returning dummy resource name")
    return f"projects/debug/locations/{vertex_location}/models/stub-{model_display_name}"
