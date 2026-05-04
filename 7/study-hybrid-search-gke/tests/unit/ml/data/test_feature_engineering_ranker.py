"""Parity guard for build_ranker_features — keys must equal FEATURE_COLS_RANKER."""

from ml.data.feature_engineering import FEATURE_COLS_RANKER, build_ranker_features


def test_build_ranker_features_keys_match_feature_cols_ranker() -> None:
    row = {
        "rent": 120000,
        "walk_min": 8,
        "age_years": 15,
        "area_m2": 42.5,
        "ctr": 0.12,
        "fav_rate": 0.03,
        "inquiry_rate": 0.01,
    }
    out = build_ranker_features(
        property_features=row,
        me5_score=0.87,
        lexical_rank=3,
        semantic_rank=5,
    )
    assert list(out.keys()) == FEATURE_COLS_RANKER


def test_build_ranker_features_numeric_coercion() -> None:
    out = build_ranker_features(
        property_features={
            "rent": 100_000,
            "walk_min": 5,
            "age_years": 10,
            "area_m2": 30.0,
            "ctr": 0.2,
            "fav_rate": 0.1,
            "inquiry_rate": 0.05,
        },
        me5_score=0.9,
        lexical_rank=1,
        semantic_rank=2,
    )
    assert out["rent"] == 100000.0
    assert out["me5_score"] == 0.9
    assert out["lexical_rank"] == 1.0
    assert out["semantic_rank"] == 2.0
    assert isinstance(out["rent"], float)


def test_build_ranker_features_handles_missing_behavior() -> None:
    out = build_ranker_features(
        property_features={
            "rent": 80_000,
            "walk_min": 12,
            "age_years": 25,
            "area_m2": 20.0,
            "ctr": None,
            "fav_rate": None,
            "inquiry_rate": None,
        },
        me5_score=0.5,
        lexical_rank=50,
        semantic_rank=60,
    )
    assert out["ctr"] == 0.0
    assert out["fav_rate"] == 0.0
    assert out["inquiry_rate"] == 0.0
