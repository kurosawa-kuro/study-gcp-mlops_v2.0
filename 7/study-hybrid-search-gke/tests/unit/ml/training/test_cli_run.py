"""End-to-end wiring tests for train.cli.run."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from ml.training import model_builder as rank_cli
from ml.training.model_builder import split_by_request_id as _split_by_request_id
from ml.training.trainer import run


class _InMemoryRepo:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df
        self.saved_runs: list[dict[str, Any]] = []

    def fetch_training_rows(self, *, window_days: int) -> pd.DataFrame:
        return self._df.copy()

    def save_run(
        self,
        *,
        run_id: str,
        started_at: datetime,
        finished_at: datetime,
        model_path: str,
        metrics: dict[str, float],
        hyperparams: dict[str, object],
        git_sha: str | None = None,
        dataset_version: str | None = None,
    ) -> None:
        self.saved_runs.append(
            {
                "run_id": run_id,
                "model_path": model_path,
                "metrics": metrics,
                "hyperparams": hyperparams,
            }
        )

    def latest_model_path(self) -> str | None:
        return self.saved_runs[-1]["model_path"] if self.saved_runs else None


class _StubUploader:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def upload(self, local_dir: Path, *, run_id: str, date_str: str) -> str:
        self.calls.append({"local_dir": local_dir, "run_id": run_id, "date_str": date_str})
        return f"gs://stub/lgbm/{date_str}/{run_id}/model.txt"


class _StubTracker:
    def __init__(self) -> None:
        self.logged: list[dict[str, float]] = []

    def __enter__(self) -> _StubTracker:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def log_metrics(self, metrics: dict[str, float]) -> None:
        self.logged.append(metrics)


def _tracker_factory(_run_id: str, _workdir: Path) -> _StubTracker:
    return _StubTracker()


def test_split_by_request_id_keeps_groups_intact() -> None:
    df = rank_cli.synthetic_ranking_frames()[0]
    train_df, test_df = _split_by_request_id(df)
    # No request_id appears in both sides.
    shared = set(train_df["request_id"]) & set(test_df["request_id"])
    assert not shared


def test_split_by_request_id_empty() -> None:
    empty = pd.DataFrame(columns=["request_id"])
    t, e = _split_by_request_id(empty)
    assert t.empty and e.empty


def test_run_non_dry_run_happy_path(tmp_path: Path) -> None:
    synthetic_train, synthetic_test = rank_cli.synthetic_ranking_frames()
    full = pd.concat([synthetic_train, synthetic_test], ignore_index=True)
    repo = _InMemoryRepo(full)
    uploader = _StubUploader()

    model_uri = run(
        dry_run=False,
        save_to=str(tmp_path / "smoke.txt"),
        window_days=30,
        repository=repo,
        uploader=uploader,
        tracker_factory=_tracker_factory,
    )

    assert model_uri.startswith("gs://stub/lgbm/")
    assert uploader.calls, "uploader.upload was not invoked"
    assert repo.saved_runs, "repository.save_run was not invoked"
    saved = repo.saved_runs[-1]
    assert "ndcg_at_10" in saved["metrics"]
    assert "lambdarank_truncation_level" in saved["hyperparams"]


def test_run_non_dry_run_raises_on_empty_dataset() -> None:
    repo = _InMemoryRepo(pd.DataFrame())

    with pytest.raises(RuntimeError, match="No ranker training rows"):
        run(
            dry_run=False,
            repository=repo,
            uploader=_StubUploader(),
            tracker_factory=_tracker_factory,
        )


def test_run_dry_run_skips_upload_and_save(tmp_path: Path) -> None:
    repo = _InMemoryRepo(pd.DataFrame())
    uploader = _StubUploader()

    result = run(
        dry_run=True,
        save_to=str(tmp_path / "smoke.txt"),
        repository=repo,
        uploader=uploader,
        tracker_factory=_tracker_factory,
    )

    assert Path(result).is_file()
    assert not uploader.calls
    assert not repo.saved_runs


def _frozen_time(*_a: object, **_kw: object) -> datetime:
    return datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
