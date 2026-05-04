"""KFP component: describe a Vertex Batch Prediction embedding step."""

import json
from pathlib import Path

from kfp import dsl


@dsl.component(base_image="python:3.12")
def batch_predict_embeddings(
    project_id: str,
    vertex_location: str,
    endpoint_resource_name: str,
    model_resource_name: str,
    machine_type: str,
    input_selection: dsl.Input[dsl.Dataset],
    predictions: dsl.Output[dsl.Dataset],
) -> None:
    payload = {
        "component": "batch_predict_embeddings",
        "project_id": project_id,
        "vertex_location": vertex_location,
        "endpoint_resource_name": endpoint_resource_name,
        "model_resource_name": model_resource_name,
        "machine_type": machine_type,
        "input_selection_uri": input_selection.uri,
        "input_selection_path": input_selection.path,
        "prediction_format": {
            "instances": {"text": "string", "kind": "passage"},
            "predictions": "list[float]",
        },
    }
    predictions.metadata.update(payload)
    Path(predictions.path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
