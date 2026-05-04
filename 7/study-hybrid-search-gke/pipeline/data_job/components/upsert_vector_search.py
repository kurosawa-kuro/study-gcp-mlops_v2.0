"""KFP component: emit upsert manifest for Vertex AI Vector Search (Phase 7 PR-3).

Mirrors ``write_embeddings`` shape — the component emits a JSON manifest
describing the upsert plan (predictions URI + index resource + batch
size). A downstream runner (Cloud Function on artifact creation, or the
``scripts/setup/backfill_vector_search_index.py`` one-off Wave 2 will
add) consumes the manifest, reads the predictions JSONL, and calls
``VertexVectorSearchWriter.upsert`` to push to the serving-side index.

Why a manifest rather than calling the SDK in-process: KFP components
run in a generic container; pulling the full
``google-cloud-aiplatform[v1beta1]`` SDK there bloats startup. The
existing ``write_embeddings`` component follows the same pattern (emits
a MERGE manifest, downstream BQ runner executes it).

Wired into the embed DAG only when ``enable_vector_search_upsert=True``
is passed to ``property_search_embed_pipeline`` (default ``False`` —
Strangler 原則, see ``docs/tasks/TASKS_ROADMAP.md`` §3.3).
"""

import json
from pathlib import Path

from kfp import dsl


@dsl.component(base_image="python:3.12")
def upsert_vector_search(
    project_id: str,
    vertex_location: str,
    index_resource_name: str,
    predictions: dsl.Input[dsl.Dataset],
    upsert_manifest: dsl.Output[dsl.Artifact],
    batch_size: int = 500,
) -> None:
    payload = {
        "component": "upsert_vector_search",
        "project_id": project_id,
        "vertex_location": vertex_location,
        "index_resource_name": index_resource_name,
        "predictions_uri": predictions.uri,
        "batch_size": batch_size,
    }
    upsert_manifest.metadata.update(payload)
    Path(upsert_manifest.path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
