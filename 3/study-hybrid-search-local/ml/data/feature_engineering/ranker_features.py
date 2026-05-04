"""Inference-side feature engineering — ranker only.

:func:`build_ranker_features` assembles the 10-column ranker feature vector
from (a) a row fetched from ``feature_mart.property_features_daily``, plus
(b) query-time signals ``me5_score`` and rank signals. Output keys must
equal ``FEATURE_COLS_RANKER`` in :mod:`ml.data.feature_engineering.schema`.

Pure function — no GCP SDK imports, no file I/O — so it stays trivially
testable and can run in both the API and the training pipeline.
"""

from __future__ import annotations

from typing import Any

from .schema import FEATURE_COLS_RANKER


def build_ranker_features(
    *,
    property_features: dict[str, Any],
    me5_score: float,
    lexical_rank: int,
    semantic_rank: int,
) -> dict[str, float]:
    """Assemble the 10-column ranker feature dict (keys == FEATURE_COLS_RANKER).

    ``property_features`` is a row from ``feature_mart.property_features_daily``;
    query-time ``me5_score`` / ``lexical_rank`` / ``semantic_rank`` are computed
    online during /search.
    Missing behavioral signals default to 0.0 — acceptable because the ranker
    treats zero as 'no signal' (cold-start) and the fallback popularity score
    handles the extreme case.
    """
    out: dict[str, float] = {
        "rent": float(property_features.get("rent") or 0.0),
        "walk_min": float(property_features.get("walk_min") or 0.0),
        "age_years": float(property_features.get("age_years") or 0.0),
        "area_m2": float(property_features.get("area_m2") or 0.0),
        "ctr": float(property_features.get("ctr") or 0.0),
        "fav_rate": float(property_features.get("fav_rate") or 0.0),
        "inquiry_rate": float(property_features.get("inquiry_rate") or 0.0),
        "me5_score": float(me5_score),
        "lexical_rank": float(lexical_rank),
        "semantic_rank": float(semantic_rank),
    }
    assert list(out.keys()) == FEATURE_COLS_RANKER
    return out
