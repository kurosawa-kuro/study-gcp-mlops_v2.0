"""Shared feature / label schema for the real-estate ranker.

Parity-locked files for this 10-column set:

1. ``pipeline/data_job/dataform/features/property_features_daily.sqlx``  (training SQL)
2. ``ml/data/feature_engineering/ranker_features.py::build_ranker_features``  (serving)
3. THIS file — ``FEATURE_COLS_RANKER`` / ``LABEL_GAIN``
4. ``infra/terraform/modules/data/main.tf``  (``ranking_log.features`` RECORD)
5. ``infra/terraform/modules/monitoring/assets/validate_feature_skew.sql``  (drift UNPIVOT)
6. ``infra/terraform/modules/vertex/main.tf``  (Feature Group property-side feature declarations)

A single added/renamed/reordered feature must touch all 6 files in the same
PR; ``tests/unit/parity/test_feature_parity_ranking.py`` +
``tests/unit/parity/test_feature_parity_sql_ranker.py`` fail fast on drift.
"""

FEATURE_COLS_RANKER: list[str] = [
    "rent",
    "walk_min",
    "age_years",
    "area_m2",
    "ctr",
    "fav_rate",
    "inquiry_rate",
    "me5_score",
    "lexical_rank",
    "semantic_rank",
]

RANKER_GROUP_COL: str = "request_id"
RANKER_LABEL_COL: str = "label"

# LambdaRank gain per user action. Higher = stronger positive signal.
LABEL_GAIN: dict[str, int] = {
    "inquiry": 3,
    "favorite": 2,
    "click": 1,
    "none": 0,
}
