"""BQ-backed adapter for :class:`app.services.protocols.retrain_queries.RetrainQueries`.

Ranker-only after Phase 10b. Reads ``mlops.training_runs`` for run metadata
and ``mlops.feedback_events`` for the new-feedback-row counter.
"""

from __future__ import annotations

from datetime import datetime

from google.cloud import bigquery


class BigQueryRetrainQueries:
    """BQ-backed :class:`RetrainQueries` adapter."""

    def __init__(
        self,
        *,
        client: bigquery.Client,
        training_runs_table: str,
    ) -> None:
        self._client = client
        self._training_runs_table = training_runs_table

    def last_run_finished_at(self) -> datetime | None:
        query = f"""
            SELECT MAX(finished_at) AS ts
            FROM `{self._training_runs_table}`
            WHERE finished_at IS NOT NULL
        """
        row = next(iter(self._client.query(query).result()), None)
        return row["ts"] if row and row["ts"] is not None else None

    def feedback_rows_since(self, since: datetime) -> int | None:
        """Count feedback_events rows inserted since ``since``.

        Returns None if the table does not yet exist (early staging); the
        retrain policy treats None as 'no signal'.
        """
        table = self._training_runs_table.rsplit(".", 1)[0] + ".feedback_events"
        query = f"""
            SELECT COUNT(*) AS n
            FROM `{table}`
            WHERE ts >= @since
        """
        try:
            job = self._client.query(
                query,
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[bigquery.ScalarQueryParameter("since", "TIMESTAMP", since)]
                ),
            )
            row = next(iter(job.result()))
            return int(row["n"])
        except Exception:
            return None

    def ndcg_in_window(self, *, start: datetime, end: datetime) -> float | None:
        query = f"""
            SELECT AVG(metrics.ndcg_at_10) AS avg_ndcg
            FROM `{self._training_runs_table}`
            WHERE finished_at BETWEEN @start AND @end
        """
        try:
            job = self._client.query(
                query,
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("start", "TIMESTAMP", start),
                        bigquery.ScalarQueryParameter("end", "TIMESTAMP", end),
                    ]
                ),
            )
            row = next(iter(job.result()))
            return float(row["avg_ndcg"]) if row["avg_ndcg"] is not None else None
        except Exception:
            return None


def create_retrain_queries(
    *,
    project_id: str,
    training_runs_table: str,
) -> BigQueryRetrainQueries:
    """Factory that wires :class:`BigQueryRetrainQueries` to a fresh BQ client."""
    return BigQueryRetrainQueries(
        client=bigquery.Client(project=project_id),
        training_runs_table=training_runs_table,
    )
