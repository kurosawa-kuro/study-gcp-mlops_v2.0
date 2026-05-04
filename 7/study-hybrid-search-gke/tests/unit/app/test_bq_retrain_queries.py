"""Happy-path tests for BigQueryRetrainQueries (ranker branch)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.services.adapters import BigQueryRetrainQueries


def _client_with_rows(rows: list[dict]) -> MagicMock:
    client = MagicMock()
    client.query.return_value.result.return_value = iter(rows)
    return client


def _make_q(client: MagicMock) -> BigQueryRetrainQueries:
    return BigQueryRetrainQueries(
        client=client,
        training_runs_table="mlops-dev-a.mlops.training_runs",
    )


def test_last_run_finished_at_returns_timestamp() -> None:
    ts = datetime(2026, 4, 15, 3, 5, tzinfo=timezone.utc)
    q = _make_q(_client_with_rows([{"ts": ts}]))
    assert q.last_run_finished_at() == ts


def test_last_run_finished_at_returns_none_when_null() -> None:
    q = _make_q(_client_with_rows([{"ts": None}]))
    assert q.last_run_finished_at() is None


def test_last_run_finished_at_returns_none_when_empty_result() -> None:
    q = _make_q(_client_with_rows([]))
    assert q.last_run_finished_at() is None


def test_feedback_rows_since_casts_to_int() -> None:
    client = _client_with_rows([{"n": 4321}])
    q = _make_q(client)
    since = datetime(2026, 4, 10, tzinfo=timezone.utc)
    assert q.feedback_rows_since(since) == 4321

    # verify parameter binding
    job_config = client.query.call_args.kwargs["job_config"]
    params = {p.name: p.value for p in job_config.query_parameters}
    assert params["since"] == since


def test_feedback_rows_since_returns_none_on_exception() -> None:
    client = MagicMock()
    client.query.side_effect = RuntimeError("missing table")
    q = _make_q(client)
    since = datetime(2026, 4, 10, tzinfo=timezone.utc)
    assert q.feedback_rows_since(since) is None


def test_ndcg_in_window_returns_float() -> None:
    client = _client_with_rows([{"avg_ndcg": 0.78}])
    q = _make_q(client)
    start = datetime(2026, 4, 8, tzinfo=timezone.utc)
    end = datetime(2026, 4, 15, tzinfo=timezone.utc)
    assert q.ndcg_in_window(start=start, end=end) == 0.78


def test_ndcg_in_window_returns_none_when_no_runs() -> None:
    q = _make_q(_client_with_rows([{"avg_ndcg": None}]))
    start = datetime(2026, 4, 8, tzinfo=timezone.utc)
    end = datetime(2026, 4, 15, tzinfo=timezone.utc)
    assert q.ndcg_in_window(start=start, end=end) is None
