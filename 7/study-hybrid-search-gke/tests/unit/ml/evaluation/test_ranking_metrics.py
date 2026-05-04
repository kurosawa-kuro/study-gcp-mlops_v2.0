"""Unit tests for ranking metrics (NDCG / MAP / Recall@K)."""

import numpy as np

from ml.evaluation.metrics import evaluate, mean_average_precision, ndcg_at_k, recall_at_k


def test_ndcg_perfect_ranking_is_one() -> None:
    labels = np.array([3, 2, 1, 0])
    scores = np.array([0.9, 0.7, 0.5, 0.1])
    assert ndcg_at_k(labels, scores, k=4) == 1.0


def test_ndcg_reversed_is_below_one() -> None:
    labels = np.array([3, 2, 1, 0])
    scores = np.array([0.1, 0.3, 0.7, 0.9])  # reversed
    assert ndcg_at_k(labels, scores, k=4) < 0.7


def test_ndcg_all_zero_labels_is_zero() -> None:
    labels = np.array([0, 0, 0])
    scores = np.array([0.9, 0.5, 0.1])
    assert ndcg_at_k(labels, scores, k=3) == 0.0


def test_map_relevant_at_top_is_one() -> None:
    labels = np.array([1, 1, 0, 0])
    scores = np.array([0.9, 0.8, 0.3, 0.1])
    assert mean_average_precision(labels, scores) == 1.0


def test_map_no_relevance_is_zero() -> None:
    labels = np.array([0, 0, 0])
    scores = np.array([0.9, 0.5, 0.1])
    assert mean_average_precision(labels, scores) == 0.0


def test_recall_at_k_basic() -> None:
    labels = np.array([1, 0, 1, 0, 1])
    scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
    # top-3 contains 2 of 3 relevant → recall = 2/3
    assert abs(recall_at_k(labels, scores, k=3) - 2 / 3) < 1e-9


def test_evaluate_over_groups_returns_all_three_keys() -> None:
    labels = np.array([3, 0, 2, 1, 0, 0])
    scores = np.array([0.9, 0.2, 0.8, 0.1, 0.4, 0.3])
    groups = np.array([3, 3])
    out = evaluate(labels, scores, groups, k_ndcg=3, k_recall=3)
    assert set(out.keys()) == {"ndcg_at_3", "map", "recall_at_3"}
    assert 0.0 <= out["ndcg_at_3"] <= 1.0
    assert 0.0 <= out["map"] <= 1.0
    assert 0.0 <= out["recall_at_3"] <= 1.0


def test_evaluate_empty_input() -> None:
    labels = np.array([], dtype=int)
    scores = np.array([], dtype=float)
    groups = np.array([], dtype=int)
    out = evaluate(labels, scores, groups)
    assert out == {"ndcg_at_10": 0.0, "map": 0.0, "recall_at_20": 0.0}
