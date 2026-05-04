"""Training run / validation result metadata store (BigQuery facade).

Current implementation reads from ``mlops.training_runs`` and
``mlops.validation_results`` via ``google.cloud.bigquery``; used by monitoring
scripts and the evaluation job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TrainingRun:
    run_id: str
    created_at: str
    metrics: dict[str, float]
    artifact_uri: str


class MetadataStore:
    """Minimal facade over ``mlops.training_runs`` (BigQuery)."""

    def __init__(self, *, project: str, dataset: str = "mlops") -> None:
        self._project = project
        self._dataset = dataset

    def recent_runs(self, *, limit: int = 5) -> list[dict[str, Any]]:
        from google.cloud import bigquery

        client = bigquery.Client(project=self._project)
        query = f"""
            SELECT run_id, created_at, metrics, artifact_uri
            FROM `{self._project}.{self._dataset}.training_runs`
            ORDER BY created_at DESC
            LIMIT {int(limit)}
        """
        return [dict(row) for row in client.query(query).result()]
