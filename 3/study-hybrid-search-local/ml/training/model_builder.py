"""Dataset builders for the LambdaRank trainer.

Pure helpers that produce the train/test DataFrames consumed by
:func:`ml.training.trainer.train`. Two modes:

* :func:`synthetic_ranking_frames` — deterministic fake data for ``--dry-run``
  smoke tests (no BigQuery required).
* :func:`split_by_request_id` — 80/20 split at the query-group boundary so
  NDCG metrics are not corrupted by groups straddling train/test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.data.feature_engineering import (
    FEATURE_COLS_RANKER,
    RANKER_GROUP_COL,
    RANKER_LABEL_COL,
)


def synthetic_ranking_frames(
    n_queries: int = 40,
    candidates_per_query: int = 20,
    seed: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synthetic request_id x candidate frames with LambdaRank-friendly labels."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float | int | str]] = []
    for q in range(n_queries):
        request_id = f"synreq-{q:04d}"
        for rank in range(candidates_per_query):
            rent = float(rng.uniform(50_000, 300_000))
            walk_min = float(rng.integers(1, 30))
            age_years = float(rng.integers(0, 40))
            area_m2 = float(rng.uniform(15, 120))
            ctr = float(rng.uniform(0, 0.2))
            fav_rate = float(rng.uniform(0, 0.05))
            inquiry_rate = float(rng.uniform(0, 0.03))
            me5_score = float(rng.uniform(0.3, 1.0))
            lexical_rank = float(rank + 1)
            semantic_rank = float(rng.integers(1, candidates_per_query + 1))
            score = me5_score * 3 + ctr * 10 + rng.normal(0, 0.4)
            if score > 2.5:
                label = 3
            elif score > 2.0:
                label = 2
            elif score > 1.5:
                label = 1
            else:
                label = 0
            rows.append(
                {
                    RANKER_GROUP_COL: request_id,
                    "rent": rent,
                    "walk_min": walk_min,
                    "age_years": age_years,
                    "area_m2": area_m2,
                    "ctr": ctr,
                    "fav_rate": fav_rate,
                    "inquiry_rate": inquiry_rate,
                    "me5_score": me5_score,
                    "lexical_rank": lexical_rank,
                    "semantic_rank": semantic_rank,
                    RANKER_LABEL_COL: label,
                }
            )
    df = pd.DataFrame(rows)
    df = df.sort_values(RANKER_GROUP_COL, kind="stable").reset_index(drop=True)
    assert {*FEATURE_COLS_RANKER, RANKER_LABEL_COL, RANKER_GROUP_COL}.issubset(df.columns)
    split_idx = int(n_queries * 0.8) * candidates_per_query
    return df.iloc[:split_idx].copy(), df.iloc[split_idx:].copy()


def split_by_request_id(
    df: pd.DataFrame, *, train_ratio: float = 0.8
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deterministic 80/20 split at the ``request_id`` boundary.

    ``abs(hash(request_id)) % 10 < 8`` keeps entire query-groups on one side —
    never splitting a group across train/test (would break NDCG).
    """
    if df.empty:
        return df.copy(), df.copy()
    hashes = df[RANKER_GROUP_COL].map(lambda s: abs(hash(s)) % 10)
    train_mask = hashes < int(train_ratio * 10)
    train_df = df[train_mask].reset_index(drop=True)
    test_df = df[~train_mask].reset_index(drop=True)
    return train_df, test_df
