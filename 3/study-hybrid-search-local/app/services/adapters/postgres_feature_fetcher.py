"""Phase 3 — PostgreSQL ``feature_mart_property_features_daily`` fetcher.

Phase 7 の ``FeatureOnlineStoreFetcher`` (Vertex AI Feature Online Store) を
PostgreSQL 直接 SELECT に差し替えた版。Phase 4 で BigQuery feature table、
Phase 5+ で Vertex Feature Online Store + Feature View に再差し替え可能。
"""

from __future__ import annotations

import psycopg

from app.services.protocols.feature_fetcher import FeatureFetcher, FeatureRow
from ml.common import get_logger


class PostgresFeatureFetcher(FeatureFetcher):
    def __init__(self, *, dsn: str, table: str = "feature_mart_property_features_daily") -> None:
        self._dsn = dsn
        self._table = table
        self._logger = get_logger("app.adapters.postgres_feature_fetcher")

    def fetch(self, property_ids: list[str]) -> dict[str, FeatureRow]:
        if not property_ids:
            return {}
        sql = (
            f"SELECT property_id, ctr, fav_rate, inquiry_rate "
            f"FROM {self._table} WHERE property_id = ANY(%s)"
        )
        out: dict[str, FeatureRow] = {}
        try:
            with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
                cur.execute(sql, [list(property_ids)])
                rows = cur.fetchall()
        except Exception:
            self._logger.exception("PostgresFeatureFetcher.fetch failed")
            # missing entries for all ids なら all-None を返す。
            return {pid: FeatureRow(pid, None, None, None) for pid in property_ids}

        for property_id, ctr, fav_rate, inquiry_rate in rows:
            out[str(property_id)] = FeatureRow(
                property_id=str(property_id),
                ctr=float(ctr) if ctr is not None else None,
                fav_rate=float(fav_rate) if fav_rate is not None else None,
                inquiry_rate=float(inquiry_rate) if inquiry_rate is not None else None,
            )

        # 取得できなかった id は all-None で埋める (FeatureFetcher の contract)。
        for pid in property_ids:
            if pid not in out:
                out[pid] = FeatureRow(pid, None, None, None)
        return out
