"""Feature-parity invariant for the real-estate ranker (Phase R3 — 10 cols).

Locks the 10-column ranker schema across 3 files:

1. ``ml/data/feature_engineering/schema.py`` (``FEATURE_COLS_RANKER``)
2. ``ml/data/feature_engineering/ranker_features.py`` (``build_ranker_features``)
3. ``infra/terraform/modules/data/main.tf`` (``ranking_log.features`` RECORD)

The Dataform SQLX side (``property_features_daily.sqlx``) supplies the
*behavioral* subset only (ctr / fav_rate / inquiry_rate). The remaining 6
columns come from the property master or query-time signals, so the Dataform
parity rule is a subset check rather than a full equality check.
"""

from __future__ import annotations

import re

from ml.data.feature_engineering import FEATURE_COLS_RANKER, build_ranker_features
from tests.integration.parity.parity_invariant import REPO_ROOT

INFRA_PATH = REPO_ROOT / "infra" / "terraform" / "modules" / "data" / "main.tf"
SQLX_PATH = (
    REPO_ROOT / "pipeline" / "data_job" / "dataform" / "features" / "property_features_daily.sqlx"
)

_RANKING_LOG_FEATURES_BLOCK_RE = re.compile(
    r"# Feature parity invariant[^{]*?fields\s*=\s*\[(?P<fields>.*?)\]",
    re.DOTALL,
)

_FIELD_RE = re.compile(
    r'\{\s*name\s*=\s*"(?P<name>[^"]+)"\s*,\s*type\s*=\s*"(?P<type>[^"]+)"\s*,\s*mode\s*=\s*"(?P<mode>[^"]+)"'
)


def _extract_ranking_log_fields() -> list[tuple[str, str, str]]:
    text = INFRA_PATH.read_text()
    block = _RANKING_LOG_FEATURES_BLOCK_RE.search(text)
    assert block is not None, (
        "ranking_log.features RECORD with 'Feature parity invariant' marker "
        f"not found in {INFRA_PATH}"
    )
    return [(m["name"], m["type"], m["mode"]) for m in _FIELD_RE.finditer(block["fields"])]


# ---- schema.py internal consistency -------------------------------------------------


def test_feature_cols_ranker_has_ten_columns() -> None:
    assert len(FEATURE_COLS_RANKER) == 10


def test_feature_cols_ranker_no_duplicates() -> None:
    assert len(set(FEATURE_COLS_RANKER)) == len(FEATURE_COLS_RANKER)


# ---- Python build_ranker_features ↔ FEATURE_COLS_RANKER ----------------------------


def test_build_ranker_features_keys_match_schema_exactly() -> None:
    out = build_ranker_features(
        property_features={
            "rent": 100_000,
            "walk_min": 5,
            "age_years": 10,
            "area_m2": 30.0,
            "ctr": 0.1,
            "fav_rate": 0.02,
            "inquiry_rate": 0.01,
        },
        me5_score=0.8,
        lexical_rank=2,
        semantic_rank=4,
    )
    assert list(out.keys()) == FEATURE_COLS_RANKER


# ---- Terraform ranking_log.features ↔ FEATURE_COLS_RANKER --------------------------


def test_infra_ranking_log_features_order_matches_schema() -> None:
    names = [name for name, _, _ in _extract_ranking_log_fields()]
    assert names == FEATURE_COLS_RANKER, (
        f"ranking_log.features order {names} ≠ FEATURE_COLS_RANKER {FEATURE_COLS_RANKER}. "
        "Update infra/terraform/modules/data/main.tf to match feature_engineering/schema.py."
    )


def test_infra_ranking_log_features_are_float64_nullable() -> None:
    offenders = [
        (name, typ, mode)
        for name, typ, mode in _extract_ranking_log_fields()
        if typ != "FLOAT64" or mode != "NULLABLE"
    ]
    assert not offenders, (
        f"ranking_log.features must be FLOAT64 NULLABLE throughout; offenders: {offenders}"
    )


# ---- Dataform SQLX ↔ FEATURE_COLS_RANKER (behavioral subset only) ------------------


def test_dataform_property_features_has_behavioral_cols() -> None:
    """Dataform emits ctr / fav_rate / inquiry_rate; the rest come from raw/query time."""
    text = SQLX_PATH.read_text()
    for col in ("ctr", "fav_rate", "inquiry_rate"):
        assert f" AS {col}" in text, (
            f"property_features_daily.sqlx missing '{col}' column — update both "
            "the Dataform SQL and feature_schema.FEATURE_COLS_RANKER together."
        )
