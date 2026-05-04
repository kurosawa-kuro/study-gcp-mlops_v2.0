"""Pin the contract of ``VertexExperimentsTracker``.

Run 3 で `BigQueryRankerRepository._log_vertex_experiment` 内に埋め込まれて
いた `aiplatform.*` 直叩きを adapter として外出し。本テストは adapter の
振る舞いを fake `aiplatform` 経由で pin する。
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_aiplatform(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stand in for ``google.cloud.aiplatform`` so the adapter is testable
    without the real SDK / GCP credentials.
    """
    fake = MagicMock(name="aiplatform")
    fake_run_handle = MagicMock(name="aiplatform.start_run.return_value")
    fake.start_run.return_value = fake_run_handle

    google_pkg = types.ModuleType("google")
    cloud_pkg = types.ModuleType("google.cloud")
    google_pkg.cloud = cloud_pkg  # type: ignore[attr-defined]
    cloud_pkg.aiplatform = fake  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud_pkg)
    monkeypatch.setitem(sys.modules, "google.cloud.aiplatform", fake)
    return fake


def test_enter_initializes_aiplatform_and_starts_run(fake_aiplatform: MagicMock) -> None:
    from ml.training.experiments.adapters.vertex_experiments_tracker import (
        VertexExperimentsTracker,
    )

    tracker = VertexExperimentsTracker(
        project_id="mlops-test", experiment_name="exp-1", run_id="run-A"
    )
    with tracker:
        pass

    fake_aiplatform.init.assert_called_once_with(project="mlops-test", experiment="exp-1")
    fake_aiplatform.start_run.assert_called_once_with(run="run-A", resume=True)
    fake_aiplatform.start_run.return_value.__enter__.assert_called_once()
    fake_aiplatform.start_run.return_value.__exit__.assert_called_once()


def test_log_metrics_filters_non_numeric(fake_aiplatform: MagicMock) -> None:
    from ml.training.experiments.adapters.vertex_experiments_tracker import (
        VertexExperimentsTracker,
    )

    tracker = VertexExperimentsTracker(project_id="mlops-test", experiment_name="exp", run_id="r")
    with tracker:
        tracker.log_metrics({"ndcg_at_10": 0.83, "label": "skip", "best_iteration": 42})  # type: ignore[dict-item]

    fake_aiplatform.log_metrics.assert_called_once_with(
        {"ndcg_at_10": 0.83, "best_iteration": 42.0}
    )


def test_log_params_filters_non_scalar_and_none(fake_aiplatform: MagicMock) -> None:
    from ml.training.experiments.adapters.vertex_experiments_tracker import (
        VertexExperimentsTracker,
    )

    tracker = VertexExperimentsTracker(project_id="mlops-test", experiment_name="exp", run_id="r")
    with tracker:
        tracker.log_params(
            {
                "num_leaves": 31,
                "learning_rate": 0.05,
                "objective": "lambdarank",
                "feature_fraction": None,
                "extra_dict": {"nested": 1},
            }
        )

    fake_aiplatform.log_params.assert_called_once_with(
        {"num_leaves": 31, "learning_rate": 0.05, "objective": "lambdarank"}
    )


def test_exit_propagates_aiplatform_exit_then_clears_handle(fake_aiplatform: MagicMock) -> None:
    """Idempotent close — second `__exit__` must not double-call the handle."""
    from ml.training.experiments.adapters.vertex_experiments_tracker import (
        VertexExperimentsTracker,
    )

    tracker = VertexExperimentsTracker(project_id="mlops-test", experiment_name="exp", run_id="r")
    tracker.__enter__()
    tracker.__exit__(None, None, None)
    tracker.__exit__(None, None, None)  # second call: no-op

    assert fake_aiplatform.start_run.return_value.__exit__.call_count == 1


def test_satisfies_experiment_tracker_protocol(fake_aiplatform: MagicMock) -> None:
    """Static check that ``VertexExperimentsTracker`` satisfies ``ExperimentTracker``."""
    from ml.training.experiments.adapters.vertex_experiments_tracker import (
        VertexExperimentsTracker,
    )
    from ml.training.experiments.ports.experiment_tracker import ExperimentTracker

    tracker: ExperimentTracker = VertexExperimentsTracker(
        project_id="x", experiment_name="y", run_id="z"
    )
    # Protocol satisfaction ensures the repository / trainer can swap fake
    # for real without code changes. Touch each method to silence linting.
    _: Any = tracker
    assert callable(tracker.log_metrics)
    assert callable(tracker.log_params)
