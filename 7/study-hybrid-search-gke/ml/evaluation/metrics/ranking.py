"""Ranking evaluation metrics (numpy only).

Implements NDCG@K, MAP, Recall@K over per-query groups. Gain values follow the
LambdaRank convention: gain = label value (0..3) with log2 discount.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np


def _dcg(labels: np.ndarray) -> float:
    """Discounted cumulative gain with log2(rank+2) discount."""
    if labels.size == 0:
        return 0.0
    gains = (2.0**labels - 1.0).astype(float)
    discounts = np.log2(np.arange(labels.size) + 2.0)
    return float(np.sum(gains / discounts))


def ndcg_at_k(
    labels: np.ndarray,
    scores: np.ndarray,
    *,
    k: int,
) -> float:
    """NDCG@k over a single query."""
    if labels.size == 0:
        return 0.0
    order = np.argsort(-scores, kind="stable")
    ranked_labels = labels[order][:k]
    ideal_labels = np.sort(labels)[::-1][:k]
    ideal = _dcg(ideal_labels)
    if ideal == 0.0:
        return 0.0
    return _dcg(ranked_labels) / ideal


def mean_average_precision(
    labels: np.ndarray,
    scores: np.ndarray,
) -> float:
    """MAP over a single query (binary relevance: label > 0 is relevant)."""
    if labels.size == 0:
        return 0.0
    order = np.argsort(-scores, kind="stable")
    relevant = (labels[order] > 0).astype(int)
    if relevant.sum() == 0:
        return 0.0
    cum = np.cumsum(relevant)
    precisions = cum / (np.arange(relevant.size) + 1)
    return float(np.sum(precisions * relevant) / relevant.sum())


def recall_at_k(
    labels: np.ndarray,
    scores: np.ndarray,
    *,
    k: int,
) -> float:
    """Recall@k over a single query (binary relevance)."""
    if labels.size == 0:
        return 0.0
    total_relevant = int((labels > 0).sum())
    if total_relevant == 0:
        return 0.0
    order = np.argsort(-scores, kind="stable")
    top_k = labels[order][:k]
    return float((top_k > 0).sum() / total_relevant)


def _iter_groups(
    groups: np.ndarray,
) -> Iterable[tuple[int, int]]:
    """Yield (start, end) slice bounds for each consecutive group run."""
    start = 0
    for size in groups:
        yield start, start + int(size)
        start += int(size)


def evaluate(
    labels: np.ndarray,
    scores: np.ndarray,
    groups: np.ndarray,
    *,
    k_ndcg: int = 10,
    k_recall: int = 20,
) -> dict[str, float]:
    """Compute mean NDCG@k, MAP, Recall@k over groups."""
    if labels.size == 0:
        return {
            f"ndcg_at_{k_ndcg}": 0.0,
            "map": 0.0,
            f"recall_at_{k_recall}": 0.0,
        }
    ndcgs: list[float] = []
    maps: list[float] = []
    recalls: list[float] = []
    for start, end in _iter_groups(groups):
        g_labels = labels[start:end]
        g_scores = scores[start:end]
        ndcgs.append(ndcg_at_k(g_labels, g_scores, k=k_ndcg))
        maps.append(mean_average_precision(g_labels, g_scores))
        recalls.append(recall_at_k(g_labels, g_scores, k=k_recall))
    return {
        f"ndcg_at_{k_ndcg}": round(float(np.mean(ndcgs)), 4),
        "map": round(float(np.mean(maps)), 4),
        f"recall_at_{k_recall}": round(float(np.mean(recalls)), 4),
    }
