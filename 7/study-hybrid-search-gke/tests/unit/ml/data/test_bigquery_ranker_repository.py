"""Happy-path tests for BigQueryRankerRepository (Task 1 / Phase 6)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from ml.data.loaders.ranker_repository import BigQueryRankerRepository


def _make_repo(client: MagicMock) -> BigQueryRankerRepository:
    return BigQueryRankerRepository(
        client=client,
        project_id="mlops-dev-a",
        ranking_log_table="mlops-dev-a.mlops.ranking_log",
        feedback_events_table="mlops-dev-a.mlops.feedback_events",
        training_runs_table="mlops-dev-a.mlops.training_runs",
    )


def test_fetch_training_rows_builds_parameterized_query() -> None:
    client = MagicMock()
    # Simulate a tiny result frame.
    client.query.return_value.result.return_value.to_dataframe.return_value = pd.DataFrame(
        {
            "request_id": ["q1", "q1", "q2"],
            "property_id": ["P1", "P2", "P1"],
            "rent": [100.0, 120.0, 90.0],
            "walk_min": [5.0, 8.0, 3.0],
            "age_years": [10.0, 20.0, 5.0],
            "area_m2": [30.0, 25.0, 40.0],
            "ctr": [0.1, 0.05, 0.2],
            "fav_rate": [0.01, 0.0, 0.05],
            "inquiry_rate": [0.0, 0.0, 0.02],
            "me5_score": [0.8, 0.5, 0.9],
            "lexical_rank": [1.0, 2.0, 1.0],
            "label": [3, 0, 2],
        }
    )
    repo = _make_repo(client)
    df = repo.fetch_training_rows(window_days=90)

    assert len(df) == 3
    query_str = client.query.call_args.args[0]
    # Label generation discipline: strongest action wins.
    assert "COUNTIF(action = 'inquiry')" in query_str
    assert "COUNTIF(action = 'favorite')" in query_str
    assert "COUNTIF(action = 'click')" in query_str
    # ORDER BY contract — LambdaRank group sizes depend on contiguous request_id ordering.
    assert "ORDER BY r.request_id, r.lexical_rank" in query_str
    # Time window parameter is bound, not interpolated.
    job_config = client.query.call_args.kwargs["job_config"]
    params = {p.name: p.value for p in job_config.query_parameters}
    assert params["window_days"] == 90


def test_save_run_records_ranker_metrics() -> None:
    client = MagicMock()
    client.insert_rows_json.return_value = []
    repo = _make_repo(client)
    started = datetime(2026, 4, 20, 10, tzinfo=timezone.utc)
    finished = datetime(2026, 4, 20, 10, 15, tzinfo=timezone.utc)
    repo.save_run(
        run_id="20260420T100000Z-abcd1234",
        started_at=started,
        finished_at=finished,
        model_path="gs://mlops-dev-a-models/lgbm/2026-04-20/20260420T100000Z-abcd1234/model.txt",
        metrics={
            "ndcg_at_10": 0.83,
            "map": 0.42,
            "recall_at_20": 0.71,
            "best_iteration": 120,
            # Extra keys must be silently dropped.
            "rogue_metric": 9.9,
        },
        hyperparams={
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "num_iterations": 200,
            "early_stopping_rounds": 20,
            "min_data_in_leaf": 50,
            "lambdarank_truncation_level": 20,
        },
    )
    client.insert_rows_json.assert_called_once()
    call = client.insert_rows_json.call_args
    assert call.args[0] == "mlops-dev-a.mlops.training_runs"
    row = call.args[1][0]
    assert row["run_id"] == "20260420T100000Z-abcd1234"
    # Ranker-only metrics — no rmse/mae/r2 leak.
    assert set(row["metrics"].keys()) == {"best_iteration", "ndcg_at_10", "map", "recall_at_20"}
    assert row["metrics"]["ndcg_at_10"] == 0.83
    # LambdaRank-specific hyperparameters present.
    assert row["hyperparams"]["lambdarank_truncation_level"] == 20


def test_save_run_raises_on_insert_errors() -> None:
    client = MagicMock()
    client.insert_rows_json.return_value = [{"errors": [{"reason": "invalid"}]}]
    repo = _make_repo(client)
    started = datetime(2026, 4, 20, 10, tzinfo=timezone.utc)

    with pytest.raises(RuntimeError, match="insert_rows_json failed"):
        repo.save_run(
            run_id="x",
            started_at=started,
            finished_at=started,
            model_path="gs://...",
            metrics={},
            hyperparams={},
        )


def test_latest_model_path_returns_none_when_empty() -> None:
    client = MagicMock()
    client.query.return_value.result.return_value = iter([])
    assert _make_repo(client).latest_model_path() is None


def test_latest_model_path_returns_model_path() -> None:
    client = MagicMock()
    client.query.return_value.result.return_value = iter(
        [{"model_path": "gs://bkt/lgbm/2026-04-20/r1/model.txt"}]
    )
    assert _make_repo(client).latest_model_path() == "gs://bkt/lgbm/2026-04-20/r1/model.txt"


def test_save_run_dual_writes_to_vertex_experiments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERTEX_EXPERIMENT_NAME", "property-reranker-lgbm")
    client = MagicMock()
    client.insert_rows_json.return_value = []
    repo = _make_repo(client)
    started = datetime(2026, 4, 21, 10, tzinfo=timezone.utc)
    finished = datetime(2026, 4, 21, 10, 15, tzinfo=timezone.utc)

    fake_aiplatform = MagicMock()
    fake_aiplatform.start_run.return_value.__enter__.return_value = MagicMock()
    fake_aiplatform.start_run.return_value.__exit__.return_value = None
    with patch.dict(
        "sys.modules",
        {
            "google.cloud.aiplatform": fake_aiplatform,
            "google.cloud": MagicMock(aiplatform=fake_aiplatform),
        },
    ):
        repo.save_run(
            run_id="20260421T100000Z-deadbeef",
            started_at=started,
            finished_at=finished,
            model_path="gs://bkt/lgbm/2026-04-21/20260421T100000Z-deadbeef/model.txt",
            metrics={"ndcg_at_10": 0.81, "map": 0.4, "recall_at_20": 0.7, "best_iteration": 150},
            hyperparams={"num_leaves": 31, "learning_rate": 0.05},
        )

    fake_aiplatform.init.assert_called_once()
    fake_aiplatform.start_run.assert_called_once()
    assert fake_aiplatform.log_params.call_args.args[0] == {"num_leaves": 31, "learning_rate": 0.05}
    metrics_arg = fake_aiplatform.log_metrics.call_args.args[0]
    assert metrics_arg["ndcg_at_10"] == 0.81
    client.insert_rows_json.assert_called_once()


def test_save_run_skips_vertex_experiments_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERTEX_EXPERIMENT_NAME", raising=False)
    client = MagicMock()
    client.insert_rows_json.return_value = []
    repo = _make_repo(client)
    started = datetime(2026, 4, 21, 10, tzinfo=timezone.utc)

    fake_aiplatform = MagicMock()
    with patch.dict("sys.modules", {"google.cloud.aiplatform": fake_aiplatform}):
        repo.save_run(
            run_id="r",
            started_at=started,
            finished_at=started,
            model_path="gs://bkt/lgbm/2026-04-21/r/model.txt",
            metrics={"ndcg_at_10": 0.8},
            hyperparams={"num_leaves": 31},
        )

    fake_aiplatform.init.assert_not_called()
    fake_aiplatform.start_run.assert_not_called()
