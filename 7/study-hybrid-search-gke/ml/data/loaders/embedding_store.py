"""Embedding store: BigQuery-backed reader/writer for ``property_embeddings``.

Contains both the Protocol contracts (so pure code / tests can depend on the
interface without pulling ``google.cloud.bigquery``) and the BigQuery adapter
implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ml.common.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PropertyText:
    property_id: str
    title: str
    description: str


@dataclass(frozen=True)
class EmbeddingRow:
    property_id: str
    embedding: list[float]
    text_hash: str
    model_name: str
    generated_at: datetime


class PropertyTextRepository(Protocol):
    def fetch_all(self) -> list[PropertyText]: ...


class EmbeddingStore(Protocol):
    def existing_hashes(self) -> dict[str, str]: ...
    def upsert(self, rows: list[EmbeddingRow]) -> int: ...


class BigQueryPropertyTextRepository:
    """Reads property_id + title + description from properties_cleaned."""

    def __init__(
        self,
        *,
        project_id: str,
        cleaned_table: str,
        client: object | None = None,
    ) -> None:
        from google.cloud import bigquery

        self._project_id = project_id
        self._cleaned_table = cleaned_table
        self._client = client or bigquery.Client(project=project_id)

    def fetch_all(self) -> list[PropertyText]:
        query = f"""
            SELECT property_id, title, description
            FROM `{self._cleaned_table}`
            WHERE title IS NOT NULL
        """
        rows = self._client.query(query).result()  # type: ignore[attr-defined]
        return [
            PropertyText(
                property_id=r["property_id"],
                title=r["title"] or "",
                description=r["description"] or "",
            )
            for r in rows
        ]


class BigQueryEmbeddingStore:
    """BQ-backed :class:`EmbeddingStore` adapter."""

    def __init__(
        self,
        *,
        project_id: str,
        embeddings_table: str,
        client: object | None = None,
    ) -> None:
        from google.cloud import bigquery

        self._project_id = project_id
        self._embeddings_table = embeddings_table
        self._client = client or bigquery.Client(project=project_id)

    def existing_hashes(self) -> dict[str, str]:
        query = f"SELECT property_id, text_hash FROM `{self._embeddings_table}`"
        rows = self._client.query(query).result()  # type: ignore[attr-defined]
        return {r["property_id"]: r["text_hash"] for r in rows}

    def upsert(self, rows: list[EmbeddingRow]) -> int:
        from google.cloud import bigquery

        if not rows:
            return 0
        payload = [
            {
                "property_id": r.property_id,
                "embedding": r.embedding,
                "text_hash": r.text_hash,
                "model_name": r.model_name,
                "generated_at": r.generated_at.astimezone(timezone.utc).isoformat(),
            }
            for r in rows
        ]
        ids = [r.property_id for r in rows]
        delete_stmt = f"""
            DELETE FROM `{self._embeddings_table}`
            WHERE property_id IN UNNEST(@ids)
        """
        self._client.query(  # type: ignore[attr-defined]
            delete_stmt,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", ids)]
            ),
        ).result()
        errors = self._client.insert_rows_json(self._embeddings_table, payload)  # type: ignore[attr-defined]
        if errors:
            raise RuntimeError(f"BigQuery insert_rows_json failed: {errors}")
        logger.info("Upserted %d embeddings into %s", len(rows), self._embeddings_table)
        return len(rows)
