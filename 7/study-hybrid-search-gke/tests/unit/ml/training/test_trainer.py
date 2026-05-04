"""LambdaRank trainer smoke test — exercises build_rank_params + train + write_artifacts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ml.training.trainer import (
    _group_sizes,
    build_rank_params,
    train,
    write_artifacts,
)


def _synthetic_frame(n_queries: int = 10, per_query: int = 8, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for q in range(n_queries):
        for r in range(per_query):
            me5 = float(rng.uniform(0.3, 1.0))
            ctr = float(rng.uniform(0, 0.2))
            label = 3 if me5 > 0.85 else 2 if me5 > 0.7 else 1 if me5 > 0.5 else 0
            rows.append(
                {
                    "request_id": f"q{q:03d}",
                    "rent": float(rng.uniform(50_000, 200_000)),
                    "walk_min": float(rng.integers(1, 30)),
                    "age_years": float(rng.integers(0, 30)),
                    "area_m2": float(rng.uniform(20, 80)),
                    "ctr": ctr,
                    "fav_rate": float(rng.uniform(0, 0.05)),
                    "inquiry_rate": float(rng.uniform(0, 0.02)),
                    "me5_score": me5,
                    "lexical_rank": float(r + 1),
                    "semantic_rank": float(rng.integers(1, per_query + 1)),
                    "label": label,
                }
            )
    return pd.DataFrame(rows).sort_values("request_id", kind="stable").reset_index(drop=True)


def test_group_sizes_contiguous() -> None:
    df = pd.DataFrame({"request_id": ["a", "a", "b", "b", "b", "c"]})
    sizes = _group_sizes(df)
    assert list(sizes) == [2, 3, 1]


def test_group_sizes_empty() -> None:
    df = pd.DataFrame({"request_id": []})
    sizes = _group_sizes(df)
    assert sizes.size == 0


def test_rank_train_produces_booster(tmp_path: Path) -> None:
    df = _synthetic_frame()
    split = int(len(df) * 0.75)
    train_df = df.iloc[:split].copy()
    test_df = df.iloc[split:].copy()
    params = build_rank_params(
        num_leaves=7,
        learning_rate=0.1,
        feature_fraction=0.9,
        bagging_fraction=0.8,
        bagging_freq=0,
        min_data_in_leaf=5,
        lambdarank_truncation_level=10,
    )
    result = train(
        train_df=train_df,
        test_df=test_df,
        params=params,
        num_iterations=20,
        early_stopping_rounds=10,
    )
    assert result.booster.num_trees() > 0
    assert "ndcg_at_10" in result.metrics
    assert "map" in result.metrics
    assert "recall_at_20" in result.metrics

    artifacts = write_artifacts(result, output_dir=tmp_path / "art")
    assert artifacts.model_path.is_file()
    assert (artifacts.artifacts_dir / "metrics.json").is_file()
    assert (artifacts.artifacts_dir / "feature_importance.csv").is_file()
    # KServe LGBServer requires `.bst` extension — write_artifacts now
    # produces both files so the same artifact_uri serves both the CLI
    # consumers (model.txt) and the KServe Pod (model.bst). Pin both.
    bst_path = artifacts.artifacts_dir / "model.bst"
    assert bst_path.is_file(), "model.bst missing — KServe LGBServer cannot load this version"
    assert bst_path.read_bytes() == artifacts.model_path.read_bytes()


def test_rank_train_missing_columns_raises() -> None:
    df = pd.DataFrame({"request_id": ["a", "a"], "rent": [1.0, 2.0], "label": [0, 1]})
    with __import__("pytest").raises(ValueError, match="Training frame missing columns"):
        train(
            train_df=df,
            test_df=df,
            params=build_rank_params(
                num_leaves=4,
                learning_rate=0.1,
                feature_fraction=1.0,
                bagging_fraction=1.0,
                bagging_freq=0,
                min_data_in_leaf=1,
                lambdarank_truncation_level=5,
            ),
            num_iterations=3,
            early_stopping_rounds=2,
        )
