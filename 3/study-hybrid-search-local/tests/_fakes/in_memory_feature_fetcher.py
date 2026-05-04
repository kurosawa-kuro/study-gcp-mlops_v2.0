"""Deterministic in-memory ``FeatureFetcher`` stub (Phase 7 PR-2).

Used in unit / integration tests where rerank-side feature fetching needs
to be exercised without hitting BigQuery or Vertex AI Feature Online
Store. Returns a fixed feature row per known property_id; unknown IDs
get all-``None`` rows so callers see the production "missing data"
contract.
"""

from __future__ import annotations

from app.services.protocols.feature_fetcher import FeatureFetcher, FeatureRow


class InMemoryFeatureFetcher(FeatureFetcher):
    """Returns pre-loaded feature rows; records every ``fetch`` call."""

    def __init__(self, rows: dict[str, FeatureRow] | None = None) -> None:
        self._rows = dict(rows or {})
        self.calls: list[list[str]] = []

    def fetch(self, property_ids: list[str]) -> dict[str, FeatureRow]:
        self.calls.append(list(property_ids))
        out: dict[str, FeatureRow] = {}
        for pid in property_ids:
            existing = self._rows.get(pid)
            if existing is not None:
                out[pid] = existing
            else:
                out[pid] = FeatureRow(property_id=pid, ctr=None, fav_rate=None, inquiry_rate=None)
        return out
