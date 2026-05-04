"""Retrain-trigger evaluator (pure policy logic).

Ranker branch (post-Phase 10b):
    (a) new ``mlops.feedback_events`` rows since last run >
        ``NEW_FEEDBACK_ROWS_THRESHOLD``
    (b) recent NDCG@10 dropped by ``NDCG_DEGRADATION`` absolute vs 7 days ago

Safety net:
    (c) last training run older than ``STALE_DAYS``

The data-access Port is :class:`app.services.protocols.retrain_queries.RetrainQueries`; the
concrete BQ adapter lives in :mod:`app.services.adapters.retrain`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.protocols.retrain_queries import RetrainQueries

NEW_FEEDBACK_ROWS_THRESHOLD: int = 10_000
NDCG_DEGRADATION: float = 0.03  # absolute drop (NDCG ∈ [0, 1])
STALE_DAYS: int = 7


@dataclass(frozen=True)
class RetrainThresholds:
    """Bundled trigger thresholds; defaults are the non-negotiable values."""

    new_feedback_rows_threshold: int = NEW_FEEDBACK_ROWS_THRESHOLD
    ndcg_degradation: float = NDCG_DEGRADATION
    stale_days: int = STALE_DAYS


@dataclass(frozen=True)
class RetrainDecision:
    should_retrain: bool
    reasons: list[str]
    feedback_rows_since_last: int | None
    ndcg_current: float | None
    ndcg_week_ago: float | None
    last_run_finished_at: datetime | None


def evaluate(
    queries: RetrainQueries,
    *,
    now: datetime | None = None,
    thresholds: RetrainThresholds | None = None,
) -> RetrainDecision:
    now = now or datetime.now(timezone.utc)
    thresholds = thresholds or RetrainThresholds()
    last = queries.last_run_finished_at()
    reasons: list[str] = []

    # --- (a) new feedback rows -----------------------------------------------
    since = last or (now - timedelta(days=30))
    feedback_rows = queries.feedback_rows_since(since)
    if feedback_rows is not None and feedback_rows > thresholds.new_feedback_rows_threshold:
        reasons.append(f"feedback_rows={feedback_rows}>{thresholds.new_feedback_rows_threshold}")

    # --- (b) NDCG degradation ------------------------------------------------
    ndcg_now = queries.ndcg_in_window(start=now - timedelta(days=3), end=now)
    ndcg_week_ago = queries.ndcg_in_window(
        start=now - timedelta(days=10), end=now - timedelta(days=7)
    )
    if ndcg_now is not None and ndcg_week_ago is not None:
        delta = ndcg_week_ago - ndcg_now  # positive value = degradation
        if delta >= thresholds.ndcg_degradation:
            reasons.append(f"ndcg_drop={delta:.3f}>={thresholds.ndcg_degradation}")

    # --- (c) Safety net: staleness -------------------------------------------
    if last is None:
        reasons.append("no_prior_run")
    elif now - last > timedelta(days=thresholds.stale_days):
        age = (now - last).days
        reasons.append(f"last_run_age_days={age}>{thresholds.stale_days}")

    return RetrainDecision(
        should_retrain=bool(reasons),
        reasons=reasons,
        feedback_rows_since_last=feedback_rows,
        ndcg_current=ndcg_now,
        ndcg_week_ago=ndcg_week_ago,
        last_run_finished_at=last,
    )
