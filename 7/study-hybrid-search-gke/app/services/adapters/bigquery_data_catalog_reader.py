"""BigQuery-backed developer preview of training / serving data tables."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from google.cloud import bigquery

from app.services.protocols.data_catalog_reader import (
    DataCatalogReader,
    DataCatalogSnapshot,
    DataCatalogTablePreview,
)


class BigQueryDataCatalogReader(DataCatalogReader):
    def __init__(
        self,
        *,
        client: bigquery.Client,
        properties_table: str,
        features_table: str,
        embeddings_table: str,
        ranking_log_table: str,
        training_runs_table: str,
    ) -> None:
        self._client = client
        self._properties_table = properties_table
        self._features_table = features_table
        self._embeddings_table = embeddings_table
        self._ranking_log_table = ranking_log_table
        self._training_runs_table = training_runs_table

    def read_snapshot(self) -> DataCatalogSnapshot:
        return DataCatalogSnapshot(
            tables=[
                self._properties_preview(),
                self._features_preview(),
                self._embeddings_preview(),
                self._ranking_log_preview(),
                self._training_runs_preview(),
            ]
        )

    def _properties_preview(self) -> DataCatalogTablePreview:
        rows = self._query(
            f"""
            SELECT
              property_id,
              title,
              city,
              ward,
              layout,
              rent,
              walk_min,
              age_years,
              area_m2,
              pet_ok
            FROM `{self._properties_table}`
            ORDER BY property_id
            LIMIT 12
            """
        )
        return DataCatalogTablePreview(
            key="properties_cleaned",
            title="物件マスタ",
            description="検索結果カードに出す物件基本情報。学習特徴量の join 元でもあります。",
            table_fqn=self._properties_table,
            latest_marker=None,
            columns=[
                "property_id",
                "title",
                "city",
                "ward",
                "layout",
                "rent",
                "walk_min",
                "age_years",
                "area_m2",
                "pet_ok",
            ],
            rows=rows,
        )

    def _features_preview(self) -> DataCatalogTablePreview:
        latest = self._scalar(
            f"SELECT CAST(MAX(event_date) AS STRING) FROM `{self._features_table}`"
        )
        rows = self._query(
            f"""
            SELECT
              CAST(event_date AS STRING) AS event_date,
              property_id,
              rent,
              walk_min,
              age_years,
              area_m2,
              ctr,
              fav_rate,
              inquiry_rate
            FROM `{self._features_table}`
            WHERE event_date = (SELECT MAX(event_date) FROM `{self._features_table}`)
            ORDER BY property_id
            LIMIT 12
            """
        )
        return DataCatalogTablePreview(
            key="property_features_daily",
            title="学習特徴量",
            description="LightGBM reranker 学習と online rerank feature parity の正本です。",
            table_fqn=self._features_table,
            latest_marker=latest,
            columns=[
                "event_date",
                "property_id",
                "rent",
                "walk_min",
                "age_years",
                "area_m2",
                "ctr",
                "fav_rate",
                "inquiry_rate",
            ],
            rows=rows,
        )

    def _ranking_log_preview(self) -> DataCatalogTablePreview:
        latest = self._scalar(f"SELECT CAST(MAX(ts) AS STRING) FROM `{self._ranking_log_table}`")
        rows = self._query(
            f"""
            SELECT
              CAST(ts AS STRING) AS ts,
              request_id,
              property_id,
              lexical_rank,
              semantic_rank,
              final_rank,
              score,
              me5_score,
              features.rent AS rent,
              features.walk_min AS walk_min
            FROM `{self._ranking_log_table}`
            ORDER BY ts DESC
            LIMIT 12
            """
        )
        return DataCatalogTablePreview(
            key="ranking_log",
            title="オンライン学習ログ",
            description="`/search` 実行時の候補群。offline 再学習と drift 監視の入力になります。",
            table_fqn=self._ranking_log_table,
            latest_marker=latest,
            columns=[
                "ts",
                "request_id",
                "property_id",
                "lexical_rank",
                "semantic_rank",
                "final_rank",
                "score",
                "me5_score",
                "rent",
                "walk_min",
            ],
            rows=rows,
        )

    def _embeddings_preview(self) -> DataCatalogTablePreview:
        latest = self._scalar(
            f"SELECT CAST(MAX(generated_at) AS STRING) FROM `{self._embeddings_table}`"
        )
        rows = self._query(
            f"""
            SELECT
              property_id,
              model_name,
              CAST(generated_at AS STRING) AS generated_at,
              ARRAY_LENGTH(embedding) AS vector_dim,
              TO_JSON_STRING(ARRAY_SLICE(embedding, 0, 3)) AS sample_head
            FROM `{self._embeddings_table}`
            ORDER BY generated_at DESC
            LIMIT 12
            """
        )
        return DataCatalogTablePreview(
            key="property_embeddings",
            title="埋め込みベクトル",
            description="semantic 検索の正本ベクトル。全文は重いので次元数と先頭 3 要素だけ preview します。",
            table_fqn=self._embeddings_table,
            latest_marker=latest,
            columns=[
                "property_id",
                "model_name",
                "generated_at",
                "vector_dim",
                "sample_head",
            ],
            rows=rows,
        )

    def _training_runs_preview(self) -> DataCatalogTablePreview:
        latest = self._scalar(
            f"SELECT CAST(MAX(started_at) AS STRING) FROM `{self._training_runs_table}`"
        )
        rows = self._query(
            f"""
            SELECT
              run_id,
              CAST(started_at AS STRING) AS started_at,
              CAST(finished_at AS STRING) AS finished_at,
              model_path,
              git_sha,
              dataset_version,
              metrics.ndcg_at_10 AS ndcg_at_10,
              metrics.recall_at_20 AS recall_at_20
            FROM `{self._training_runs_table}`
            ORDER BY started_at DESC
            LIMIT 12
            """
        )
        return DataCatalogTablePreview(
            key="training_runs",
            title="学習実行履歴",
            description="reranker 学習の実行履歴。最新モデルの系譜と評価指標を確認できます。",
            table_fqn=self._training_runs_table,
            latest_marker=latest,
            columns=[
                "run_id",
                "started_at",
                "finished_at",
                "model_path",
                "git_sha",
                "dataset_version",
                "ndcg_at_10",
                "recall_at_20",
            ],
            rows=rows,
        )

    def _scalar(self, sql: str) -> str | None:
        rows = list(self._client.query(sql).result())
        if not rows:
            return None
        value = rows[0][0]
        return None if value is None else str(value)

    def _query(self, sql: str) -> list[dict[str, object | None]]:
        rows = list(self._client.query(sql).result())
        if not rows:
            return []
        return [self._row_to_dict(row, columns=row.keys()) for row in rows]

    @staticmethod
    def _row_to_dict(
        row: Sequence[object] | Any,
        *,
        columns: Sequence[str],
    ) -> dict[str, object | None]:
        return {
            col: BigQueryDataCatalogReader._jsonish(row[idx]) for idx, col in enumerate(columns)
        }

    @staticmethod
    def _jsonish(value: object | None) -> object | None:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)
