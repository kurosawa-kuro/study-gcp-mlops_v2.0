"""KFP component: select properties that require embedding refresh."""

import json
from pathlib import Path

from kfp import dsl


@dsl.component(base_image="python:3.12")
def load_properties(
    project_id: str,
    dataset_id: str,
    source_table: str,
    embedding_table: str,
    as_of_date: str,
    full_refresh: bool,
    selection: dsl.Output[dsl.Dataset],
) -> None:
    query = f"""
    SELECT
      property_id,
      title,
      description,
      TO_HEX(SHA256(CONCAT(COALESCE(title, ''), ' ', COALESCE(description, '')))) AS text_hash
    FROM `{project_id}.{dataset_id}.{source_table}` src
    WHERE {"TRUE" if full_refresh else f"NOT EXISTS (SELECT 1 FROM `{project_id}.{dataset_id}.{embedding_table}` emb WHERE emb.property_id = src.property_id AND emb.text_hash = TO_HEX(SHA256(CONCAT(COALESCE(src.title, ''), ' ', COALESCE(src.description, '')))))"}
    """.strip()

    payload = {
        "component": "load_properties",
        "project_id": project_id,
        "dataset_id": dataset_id,
        "source_table": source_table,
        "embedding_table": embedding_table,
        "as_of_date": as_of_date,
        "full_refresh": full_refresh,
        "query": query,
    }
    selection.metadata.update(payload)
    Path(selection.path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
