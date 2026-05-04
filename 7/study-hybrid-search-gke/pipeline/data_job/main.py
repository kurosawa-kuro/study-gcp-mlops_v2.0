"""Data job: KFP property-text embedding pipeline definition + compile CLI.

Invoked by:

* ``python -m pipeline.data_job.main compile``  — KFP compile → YAML
* ``python -m pipeline.data_job.main submit``   — Vertex PipelineJob submit
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from kfp import dsl

from pipeline.data_job.components import (
    batch_predict_embeddings,
    load_properties,
    upsert_vector_search,
    write_embeddings,
)

PIPELINE_NAME = "property-search-embed"


@dsl.pipeline(name=PIPELINE_NAME, description="Property text embedding refresh pipeline")
def property_search_embed_pipeline(
    project_id: str = "mlops-dev-a",
    vertex_location: str = "asia-northeast1",
    dataset_id: str = "feature_mart",
    source_table: str = "properties_cleaned",
    embedding_table: str = "property_embeddings",
    endpoint_resource_name: str = "",
    model_resource_name: str = "",
    as_of_date: str = "",
    full_refresh: bool = False,
    prediction_machine_type: str = "n1-standard-4",
    enable_vector_search_upsert: bool = False,
    vector_search_index_resource_name: str = "",
    vector_search_upsert_batch_size: int = 500,
) -> None:
    load_task = load_properties(
        project_id=project_id,
        dataset_id=dataset_id,
        source_table=source_table,
        embedding_table=embedding_table,
        as_of_date=as_of_date,
        full_refresh=full_refresh,
    )
    predict_task = batch_predict_embeddings(
        project_id=project_id,
        vertex_location=vertex_location,
        endpoint_resource_name=endpoint_resource_name,
        model_resource_name=model_resource_name,
        machine_type=prediction_machine_type,
        input_selection=load_task.outputs["selection"],
    )
    write_embeddings(
        project_id=project_id,
        dataset_id=dataset_id,
        target_table=embedding_table,
        predictions=predict_task.outputs["predictions"],
    )
    # Phase 7 PR-3 — Vertex Vector Search 二重書き component.
    # 常に DAG に含めるが、`vector_search_index_resource_name` が空なら downstream
    # runner が manifest を見て no-op で skip する (Strangler 原則: default off)。
    # ``enable_vector_search_upsert`` は manifest にメタデータとして乗せ、Cloud
    # Function 側 gate で消費する設計 (Wave 2 で実装)。
    upsert_vector_search(
        project_id=project_id,
        vertex_location=vertex_location,
        index_resource_name=vector_search_index_resource_name,
        predictions=predict_task.outputs["predictions"],
        batch_size=vector_search_upsert_batch_size,
    )


def build_pipeline_spec() -> dict[str, object]:
    return {
        "name": PIPELINE_NAME,
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
            "enable_vector_search_upsert": False,
            "vector_search_index_resource_name": "",
            "vector_search_upsert_batch_size": 500,
        },
        "steps": [
            "load_properties",
            "batch_predict_embeddings",
            "write_embeddings",
            "upsert_vector_search",
        ],
    }


def get_pipeline() -> Any:
    return property_search_embed_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="property-search-embed pipeline CLI")
    parser.add_argument("action", choices=["compile", "submit"], default="compile", nargs="?")
    parser.add_argument("--output-dir", default="dist/pipelines")
    args = parser.parse_args(argv)

    from pipeline.workflow.compile import compile_pipeline, submit_pipeline_yaml

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    template = out / f"{PIPELINE_NAME}.yaml"
    compile_pipeline(get_pipeline(), template)
    if args.action == "submit":
        submit_pipeline_yaml(PIPELINE_NAME, template, build_pipeline_spec()["parameters"])  # type: ignore[arg-type]
    print(template)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
