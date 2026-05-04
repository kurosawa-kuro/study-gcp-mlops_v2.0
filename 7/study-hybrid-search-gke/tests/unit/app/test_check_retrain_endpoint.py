from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


class _FakeQueries:
    def __init__(
        self,
        *,
        feedback_rows: int | None = None,
        ndcg_now: float | None = None,
        ndcg_week_ago: float | None = None,
    ) -> None:
        self._feedback_rows = feedback_rows
        self._ndcg_now = ndcg_now
        self._ndcg_week_ago = ndcg_week_ago

    def last_run_finished_at(self):
        return datetime.now(timezone.utc) - timedelta(hours=1)

    def feedback_rows_since(self, since):
        return self._feedback_rows

    def ndcg_in_window(self, *, start, end):
        if end > datetime.now(timezone.utc) - timedelta(days=5):
            return self._ndcg_now
        return self._ndcg_week_ago


class _RecordingTrigger:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, payload: dict[str, object]) -> None:
        self.calls.append(payload)


def test_check_retrain_does_nothing_when_fresh(app_with_search_stub):
    app = app_with_search_stub
    trigger = _RecordingTrigger()
    app.state.container = replace(
        app.state.container,
        retrain_queries=_FakeQueries(feedback_rows=100, ndcg_now=0.80, ndcg_week_ago=0.80),
        retrain_trigger_publisher=trigger,
    )

    with TestClient(app) as client:
        r = client.post("/jobs/check-retrain")
    assert r.status_code == 200
    body = r.json()
    assert body["should_retrain"] is False
    assert trigger.calls == []


def test_check_retrain_publishes_when_feedback_threshold_exceeded(app_with_search_stub):
    app = app_with_search_stub
    trigger = _RecordingTrigger()
    app.state.container = replace(
        app.state.container,
        retrain_queries=_FakeQueries(feedback_rows=20_000),  # > 10_000
        retrain_trigger_publisher=trigger,
    )

    with TestClient(app) as client:
        r = client.post("/jobs/check-retrain")
    assert r.status_code == 200
    body = r.json()
    assert body["should_retrain"] is True
    assert body["published"] is True
    assert len(trigger.calls) == 1
    assert "reasons" in trigger.calls[0]


def test_check_retrain_publishes_when_ndcg_drops(app_with_search_stub):
    app = app_with_search_stub
    trigger = _RecordingTrigger()
    app.state.container = replace(
        app.state.container,
        retrain_queries=_FakeQueries(feedback_rows=0, ndcg_now=0.70, ndcg_week_ago=0.80),
        retrain_trigger_publisher=trigger,
    )

    with TestClient(app) as client:
        r = client.post("/jobs/check-retrain")
    body = r.json()
    assert body["should_retrain"] is True
    assert any(reason.startswith("ndcg_drop=") for reason in body["reasons"])
