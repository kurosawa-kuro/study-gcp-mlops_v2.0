"""Unit tests for app.services.retrain_policy (ranker branch only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.retrain_policy import RetrainThresholds, evaluate


class FakeQueries:
    def __init__(
        self,
        *,
        last: datetime | None,
        feedback_rows: int | None = None,
        ndcg_now: float | None = None,
        ndcg_week_ago: float | None = None,
    ) -> None:
        self._last = last
        self._feedback_rows = feedback_rows
        self._ndcg_now = ndcg_now
        self._ndcg_week_ago = ndcg_week_ago

    def last_run_finished_at(self) -> datetime | None:
        return self._last

    def feedback_rows_since(self, since: datetime) -> int | None:
        return self._feedback_rows

    def ndcg_in_window(self, *, start: datetime, end: datetime) -> float | None:
        # 「end が NOW 前後の window なら最新 NDCG、それ以前なら古い NDCG」を
        # テストフィクスチャで判定する。wall clock 依存は避け、NOW (テスト用
        # 固定値) からの差分で判定する。
        if end > NOW - timedelta(days=5):
            return self._ndcg_now
        return self._ndcg_week_ago


NOW = datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc)


def test_no_reason_no_retrain() -> None:
    q = FakeQueries(
        last=NOW - timedelta(days=1),
        feedback_rows=500,
        ndcg_now=0.80,
        ndcg_week_ago=0.80,
    )
    d = evaluate(q, now=NOW)
    assert d.should_retrain is False
    assert d.reasons == []


def test_feedback_rows_trigger() -> None:
    q = FakeQueries(
        last=NOW - timedelta(hours=6),
        feedback_rows=15_000,
        ndcg_now=None,
        ndcg_week_ago=None,
    )
    d = evaluate(q, now=NOW)
    assert d.should_retrain is True
    assert any(r.startswith("feedback_rows=15000") for r in d.reasons)


def test_feedback_rows_below_threshold_does_not_trigger() -> None:
    q = FakeQueries(
        last=NOW - timedelta(hours=6),
        feedback_rows=5_000,
    )
    assert evaluate(q, now=NOW).should_retrain is False


def test_ndcg_drop_triggers_retrain() -> None:
    q = FakeQueries(
        last=NOW - timedelta(days=1),
        ndcg_now=0.70,
        ndcg_week_ago=0.75,
    )
    d = evaluate(q, now=NOW)
    assert d.should_retrain is True
    assert any(r.startswith("ndcg_drop=") for r in d.reasons)


def test_ndcg_improvement_does_not_trigger() -> None:
    q = FakeQueries(
        last=NOW - timedelta(days=1),
        ndcg_now=0.80,
        ndcg_week_ago=0.75,
    )
    assert evaluate(q, now=NOW).should_retrain is False


def test_ndcg_missing_does_not_trigger() -> None:
    q = FakeQueries(
        last=NOW - timedelta(days=1),
        ndcg_now=None,
        ndcg_week_ago=0.75,
    )
    assert evaluate(q, now=NOW).should_retrain is False


def test_ndcg_small_drop_below_threshold() -> None:
    """0.02 drop doesn't cross default 0.03 threshold."""
    q = FakeQueries(
        last=NOW - timedelta(days=1),
        ndcg_now=0.73,
        ndcg_week_ago=0.75,
    )
    assert evaluate(q, now=NOW).should_retrain is False


def test_custom_ndcg_threshold_flips_decision() -> None:
    q = FakeQueries(
        last=NOW - timedelta(days=1),
        ndcg_now=0.73,
        ndcg_week_ago=0.75,
    )
    d = evaluate(q, now=NOW, thresholds=RetrainThresholds(ndcg_degradation=0.01))
    assert d.should_retrain is True
    assert any(r.startswith("ndcg_drop=") for r in d.reasons)


def test_staleness_trigger() -> None:
    q = FakeQueries(
        last=NOW - timedelta(days=8),
        feedback_rows=0,
        ndcg_now=0.80,
        ndcg_week_ago=0.80,
    )
    d = evaluate(q, now=NOW)
    assert d.should_retrain is True
    assert any(r.startswith("last_run_age_days=") for r in d.reasons)


def test_no_prior_run_triggers() -> None:
    q = FakeQueries(last=None, feedback_rows=None, ndcg_now=None, ndcg_week_ago=None)
    d = evaluate(q, now=NOW)
    assert d.should_retrain is True
    assert "no_prior_run" in d.reasons


def test_custom_feedback_threshold() -> None:
    q = FakeQueries(
        last=NOW - timedelta(hours=6),
        feedback_rows=500,
    )
    assert evaluate(q, now=NOW).should_retrain is False
    d = evaluate(q, now=NOW, thresholds=RetrainThresholds(new_feedback_rows_threshold=100))
    assert d.should_retrain is True
    assert any(r.startswith("feedback_rows=500>100") for r in d.reasons)


def test_custom_stale_days_triggers_on_shorter_window() -> None:
    q = FakeQueries(
        last=NOW - timedelta(days=2),
        feedback_rows=0,
    )
    assert evaluate(q, now=NOW).should_retrain is False
    d = evaluate(q, now=NOW, thresholds=RetrainThresholds(stale_days=1))
    assert d.should_retrain is True
    assert any(r.startswith("last_run_age_days=2>1") for r in d.reasons)


def test_decision_exposes_ranker_fields() -> None:
    q = FakeQueries(
        last=NOW - timedelta(hours=2),
        feedback_rows=500,
        ndcg_now=0.80,
        ndcg_week_ago=0.78,
    )
    d = evaluate(q, now=NOW)
    assert d.feedback_rows_since_last == 500
    assert d.ndcg_current == 0.80
    assert d.ndcg_week_ago == 0.78
