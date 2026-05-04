"""Phase 6 T1 — BQML ``ML.PREDICT`` adapter for property popularity.

Queries a BOOSTED_TREE_REGRESSOR model trained by
``scripts/bqml/train_popularity.sql``. The model consumes the 7 property-
side ranker features (rent, walk_min, age_years, area_m2, ctr, fav_rate,
inquiry_rate) — same columns that already flow through parity invariant,
so no 6-file cascade is needed: this adapter only *reads* those columns
during inference.

Output is an auxiliary per-property score surfaced in ``SearchResultItem
.popularity_score``. It is **not** appended to ``FEATURE_COLS_RANKER``
(doing so would break the 6-file parity invariant and force a parity
update). Using it as a rerank feature is a deliberate future step gated
on a parity-bundled PR.
"""

from __future__ import annotations

import logging

from google.cloud import bigquery

logger = logging.getLogger("app.bqml_popularity_scorer")


class BQMLPopularityScorer:
    """Predict per-property popularity via BQML ``ML.PREDICT``.

    Args:
        project_id: GCP project.
        model_fqn: fully-qualified ``project.dataset.model`` (defaults to
            ``{project_id}.mlops.property_popularity`` — matches the SQL
            in ``scripts/bqml/train_popularity.sql``).
        properties_table: fully-qualified properties_cleaned table with the
            7 property-side features (used as ML.PREDICT input source).
        features_table: fully-qualified property_features_daily table for
            the behavioural columns (ctr / fav_rate / inquiry_rate).
        client: optional pre-built BQ client (tests).
    """

    def __init__(
        self,
        *,
        project_id: str,
        model_fqn: str,
        properties_table: str,
        features_table: str,
        client: bigquery.Client | None = None,
    ) -> None:
        self._project_id = project_id
        self._model_fqn = model_fqn
        self._properties_table = properties_table
        self._features_table = features_table
        self._client = client or bigquery.Client(project=project_id)

    def score(self, property_ids: list[str]) -> dict[str, float]:
        if not property_ids:
            return {}
        query = f"""
            WITH property_batch AS (
              SELECT
                p.property_id,
                p.rent,
                p.walk_min,
                p.age_years,
                p.area_m2,
                f.ctr,
                f.fav_rate,
                f.inquiry_rate
              FROM `{self._properties_table}` p
              LEFT JOIN (
                SELECT *
                FROM `{self._features_table}`
                WHERE event_date = (SELECT MAX(event_date) FROM `{self._features_table}`)
              ) f USING (property_id)
              WHERE p.property_id IN UNNEST(@ids)
            )
            SELECT
              property_id,
              predicted_ctr AS popularity
            FROM ML.PREDICT(MODEL `{self._model_fqn}`, (SELECT * FROM property_batch))
        """
        params = [bigquery.ArrayQueryParameter("ids", "STRING", property_ids)]
        try:
            rows = self._client.query(
                query,
                job_config=bigquery.QueryJobConfig(query_parameters=params),
            ).result()
        except Exception:
            logger.exception(
                "BQML popularity predict failed model=%s n_ids=%d",
                self._model_fqn,
                len(property_ids),
            )
            raise
        out: dict[str, float] = {}
        for row in rows:
            out[str(row["property_id"])] = float(row["popularity"])
        return out
