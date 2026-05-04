"""Compile and optionally submit property-search Vertex pipelines.

Central KFP compilation utility used by each ``pipeline/*/main.py`` entrypoint.
Provides a single ``--target`` CLI so CI workflows have a uniform invocation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_SPECS: dict[str, dict[str, object]] = {
    "embed": {
        "name": "property-search-embed",
        "description": "Property text embedding batch pipeline",
        "parameters": {
            "project_id": "mlops-dev-a",
            "vertex_location": "asia-northeast1",
            "dataset_id": "feature_mart",
            "source_table": "properties_cleaned",
            "embedding_table": "property_embeddings",
            "endpoint_resource_name": "",
            "model_resource_name": "",
            "as_of_date": "",
            "full_refresh": False,
            "prediction_machine_type": "n1-standard-4",
        },
        "steps": ["load_properties", "batch_predict_embeddings", "write_embeddings"],
    },
    "train": {
        "name": "property-search-train",
        "description": "Reranker training / evaluation / registration pipeline",
        "parameters": {
            "project_id": "mlops-dev-a",
            "vertex_location": "asia-northeast1",
            "feature_dataset_id": "feature_mart",
            "feature_table": "property_features_daily",
            "mlops_dataset_id": "mlops",
            "ranking_log_table": "ranking_log",
            "feedback_events_table": "feedback_events",
            "window_days": 90,
            "trainer_image": "asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/property-trainer:latest",
            "experiment_name": "property-reranker-lgbm",
            "gate_metric_name": "ndcg_at_10",
            "gate_threshold": 0.6,
            "model_display_name": "property-reranker",
        },
        "steps": [
            "load_features",
            "train_reranker",
            "evaluate",
            "register_reranker",
        ],
    },
}


def compile_pipeline(pipeline_func: object, package_path: Path) -> Path:
    """Compile a KFP @dsl.pipeline function into a YAML template at ``package_path``."""
    from kfp.compiler import Compiler

    Compiler().compile(pipeline_func=pipeline_func, package_path=str(package_path))
    return package_path


def _target_path(root: Path, target: str) -> Path:
    if target == "embed":
        return root / "property-search-embed.yaml"
    if target == "train":
        return root / "property-search-train.yaml"
    raise ValueError(f"unknown target: {target}")


def _spec(target: str) -> dict[str, object]:
    try:
        return DEFAULT_SPECS[target]
    except KeyError as exc:
        raise ValueError(f"unknown target: {target}") from exc


def _pipeline(target: str) -> Any:
    if target == "embed":
        from pipeline.data_job.main import get_pipeline as _get

        return _get()
    if target == "train":
        from pipeline.training_job.main import get_pipeline as _get

        return _get()
    raise ValueError(f"unknown target: {target}")


def _coerce_parameter_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _merge_parameter_values(target: str, overrides: list[str]) -> dict[str, Any]:
    spec = _spec(target)
    raw_params = spec.get("parameters", {})
    assert isinstance(raw_params, dict)
    params: dict[str, Any] = dict(raw_params)
    for item in overrides:
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError(f"parameter override must be key=value: {item}")
        params[key] = _coerce_parameter_value(value)
    return params


def _submit_pipeline(
    *,
    target: str,
    template_path: Path,
    pipeline_root: str,
    project_id: str,
    location: str,
    service_account: str,
    parameter_values: dict[str, Any],
) -> str:
    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=location)
    job = aiplatform.PipelineJob(
        display_name=f"property-search-{target}",
        template_path=str(template_path),
        pipeline_root=pipeline_root,
        parameter_values=parameter_values,
        enable_caching=False,
    )
    job.submit(service_account=service_account or None)
    return job.resource_name


def submit_pipeline_yaml(
    display_name: str, template_path: Path, parameter_values: dict[str, Any]
) -> str:
    """Simple helper used by ``pipeline/*/main.py`` to submit a compiled YAML."""
    from google.cloud import aiplatform

    aiplatform.init()
    job = aiplatform.PipelineJob(
        display_name=display_name,
        template_path=str(template_path),
        parameter_values=parameter_values,
        enable_caching=False,
    )
    job.submit()
    return job.resource_name


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile property-search pipelines")
    parser.add_argument("--target", choices=["embed", "train"], required=True)
    parser.add_argument("--output-dir", default="dist/pipelines")
    parser.add_argument("--parameter", action="append", default=[])
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--project-id", default="mlops-dev-a")
    parser.add_argument("--location", default="asia-northeast1")
    parser.add_argument("--pipeline-root", default="gs://mlops-dev-a-pipeline-root/runs")
    parser.add_argument("--service-account", default="")
    parser.add_argument("--write-spec-json", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _target_path(output_dir, args.target)
    compile_pipeline(_pipeline(args.target), path)
    params = _merge_parameter_values(args.target, args.parameter)
    if args.write_spec_json:
        spec_path = path.with_suffix(".json")
        spec_payload = _spec(args.target) | {"resolved_parameters": params}
        spec_path.write_text(
            json.dumps(spec_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.submit:
        resource_name = _submit_pipeline(
            target=args.target,
            template_path=path,
            pipeline_root=args.pipeline_root,
            project_id=args.project_id,
            location=args.location,
            service_account=args.service_account,
            parameter_values=params,
        )
        print(resource_name)
        return 0
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
