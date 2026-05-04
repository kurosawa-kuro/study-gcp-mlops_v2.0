"""Port for rerank-side feature fetch (Phase 7 PR-2).

The reranker needs per-property dynamic features (``ctr`` / ``fav_rate`` /
``inquiry_rate``) at scoring time. Phase 5+ recommends serving them from
**Vertex AI Feature Online Store** (training-serving skew prevention),
while Phase 4 / fallback paths read directly from BigQuery
``feature_mart.property_features_daily``. This Port hides that choice.

Distinction from the Phase 5 Feature Group declaration:

- **Feature Group** lives on the **training** side — declares schema and
  links to the source BQ table (Terraform ``modules/vertex/main.tf``).
- **Feature Online Store + FeatureView** is the **serving** side — what
  this Port talks to in production. Source is BigQuery, but reads happen
  through the regional public endpoint with sub-100 ms latency.

PR-2 introduces the abstraction (Port + 2 adapters + fake) without
wiring it into ``Container``. PR-4 (KServe reranker → FOS opt-in) is
where the Port actually gets consumed; until then the fetcher is
constructed on demand by ``SearchBuilder._resolve_feature_fetcher`` and
returned as ``None`` when the backend is intentionally disabled.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol


class FeatureRow(NamedTuple):
    """Per-property rerank features (subset of ``FEATURE_COLS_RANKER``).

    The 3 fields here are exactly the ones served by Feature Online Store
    in production. The remaining ``FEATURE_COLS_RANKER`` entries (``rent``
    / ``walk_min`` / ``age_years`` / ``area_m2``) come from
    ``properties_cleaned`` and are not FOS-served — those stay on the
    BigQuery enrichment path inside ``BigQueryCandidateRetriever``.

    Any field can be ``None`` when:
    - the property_id is not yet in ``property_features_daily`` (cold
      start), or
    - the FOS sync has not completed (Wave 2 hourly cron).
    Downstream ``build_ranker_features`` handles ``None`` by substituting
    LightGBM-friendly defaults.
    """

    property_id: str
    ctr: float | None
    fav_rate: float | None
    inquiry_rate: float | None


class FeatureFetcher(Protocol):
    """Fetch rerank-side features for a batch of property IDs.

    Implementations must return one ``FeatureRow`` per requested ID.
    Missing properties (not present in the source) should be returned
    with all-``None`` feature values rather than omitted, so callers can
    distinguish "fetched, no data" from "not fetched". Implementations
    may raise on transport / auth failures; callers decide whether to
    fall back.
    """

    def fetch(self, property_ids: list[str]) -> dict[str, FeatureRow]: ...
