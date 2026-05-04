"""KFP component: describe MERGE of batch embeddings into BigQuery."""

import json
from pathlib import Path

from kfp import dsl


@dsl.component(base_image="python:3.12")
def write_embeddings(
    project_id: str,
    dataset_id: str,
    target_table: str,
    predictions: dsl.Input[dsl.Dataset],
    merge_manifest: dsl.Output[dsl.Artifact],
) -> None:
    merge_sql = f"""
    MERGE `{project_id}.{dataset_id}.{target_table}` tgt
    USING predictions_jsonl src
    ON tgt.property_id = src.property_id
    WHEN MATCHED THEN UPDATE SET
      embedding = src.embedding,
      text_hash = src.text_hash,
      updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (property_id, embedding, text_hash, updated_at)
      VALUES (src.property_id, src.embedding, src.text_hash, CURRENT_TIMESTAMP())
    """.strip()

    payload = {
        "component": "write_embeddings",
        "project_id": project_id,
        "dataset_id": dataset_id,
        "target_table": target_table,
        "predictions_uri": predictions.uri,
        "merge_sql": merge_sql,
    }
    merge_manifest.metadata.update(payload)
    Path(merge_manifest.path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
