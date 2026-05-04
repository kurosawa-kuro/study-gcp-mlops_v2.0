"""LightGBM LambdaRank trainer — pure training + CLI entrypoint.

Two-stage layout:

* :func:`train` — pure: consumes train/test DataFrames (must contain
  ``FEATURE_COLS_RANKER`` + ``label`` + ``request_id``), fits
  ``objective='lambdarank'``, returns the booster + metrics + hyperparams.
* :func:`write_artifacts` — I/O: persists ``model.txt`` + ``metrics.json`` +
  ``feature_importance.csv`` under ``output_dir``.
* :func:`run` / :func:`main` — orchestration: fetch BQ rows (or synthetic),
  train, upload to GCS, record to ``mlops.training_runs``. Invoked by the
  Vertex AI Pipelines training job (``pipeline.training_job.main``) and the
  ``train-reranker`` CLI.

Metrics reported: NDCG@10 (primary), MAP, Recall@20.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.common import generate_run_id, get_logger
from ml.common.config import TrainSettings
from ml.common.logging import configure_logging
from ml.data.feature_engineering import (
    FEATURE_COLS_RANKER,
    RANKER_GROUP_COL,
    RANKER_LABEL_COL,
)
from ml.data.loaders.ranker_repository import (
    RankerTrainingRepository,
    create_rank_repository,
)
from ml.evaluation.metrics import evaluate
from ml.registry.artifact_store import ArtifactUploader, GcsArtifactUploader
from ml.training.experiments import ExperimentTracker, NullExperimentTracker
from ml.training.model_builder import split_by_request_id, synthetic_ranking_frames

logger = get_logger(__name__)

TrackerFactory = Callable[[str, Path], ExperimentTracker]

TRAINING_WINDOW_DAYS: int = 90


@dataclass(frozen=True)
class RankTrainResult:
    booster: lgb.Booster
    metrics: dict[str, float]
    hyperparams: dict[str, object]


@dataclass(frozen=True)
class RankTrainingArtifacts:
    artifacts_dir: Path
    model_path: Path


def build_rank_params(
    *,
    num_leaves: int,
    learning_rate: float,
    feature_fraction: float,
    bagging_fraction: float,
    bagging_freq: int,
    min_data_in_leaf: int,
    lambdarank_truncation_level: int,
) -> dict[str, object]:
    return {
        "objective": "lambdarank",
        "metric": ["ndcg"],
        "ndcg_eval_at": [5, 10, 20],
        "lambdarank_truncation_level": lambdarank_truncation_level,
        "num_leaves": num_leaves,
        "learning_rate": learning_rate,
        "feature_fraction": feature_fraction,
        "bagging_fraction": bagging_fraction,
        "bagging_freq": bagging_freq,
        "min_data_in_leaf": min_data_in_leaf,
        "verbosity": -1,
    }


def _group_sizes(df: pd.DataFrame) -> np.ndarray:
    """Return LightGBM-style group sizes preserving the DataFrame order."""
    group_col = df[RANKER_GROUP_COL].to_numpy()
    if group_col.size == 0:
        return np.array([], dtype=int)
    boundaries = np.where(group_col[:-1] != group_col[1:])[0]
    sizes = np.diff(np.concatenate([[-1], boundaries, [group_col.size - 1]]))
    return sizes.astype(int)


def train(
    *,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    params: dict[str, object],
    num_iterations: int,
    early_stopping_rounds: int,
) -> RankTrainResult:
    """Fit a LightGBM LambdaRank booster, return booster + metrics."""
    required = [*FEATURE_COLS_RANKER, RANKER_LABEL_COL, RANKER_GROUP_COL]
    missing = [c for c in required if c not in train_df.columns]
    if missing:
        raise ValueError(f"Training frame missing columns: {missing}")

    X_train = train_df[FEATURE_COLS_RANKER].to_numpy()
    y_train = train_df[RANKER_LABEL_COL].to_numpy()
    g_train = _group_sizes(train_df)
    X_test = test_df[FEATURE_COLS_RANKER].to_numpy()
    y_test = test_df[RANKER_LABEL_COL].to_numpy()
    g_test = _group_sizes(test_df)

    train_set = lgb.Dataset(X_train, label=y_train, group=g_train, feature_name=FEATURE_COLS_RANKER)
    valid_set = lgb.Dataset(
        X_test,
        label=y_test,
        group=g_test,
        reference=train_set,
        feature_name=FEATURE_COLS_RANKER,
    )

    booster = lgb.train(
        params,
        train_set,
        num_boost_round=num_iterations,
        valid_sets=[valid_set],
        callbacks=[
            lgb.early_stopping(stopping_rounds=early_stopping_rounds),
            lgb.log_evaluation(period=20),
        ],
    )

    y_pred = np.asarray(booster.predict(X_test, num_iteration=booster.best_iteration))
    metrics = evaluate(np.asarray(y_test), y_pred, g_test, k_ndcg=10, k_recall=20)
    metrics["best_iteration"] = int(booster.best_iteration or num_iterations)

    hyperparams = {
        "num_leaves": params["num_leaves"],
        "learning_rate": params["learning_rate"],
        "feature_fraction": params["feature_fraction"],
        "bagging_fraction": params["bagging_fraction"],
        "num_iterations": num_iterations,
        "early_stopping_rounds": early_stopping_rounds,
        "min_data_in_leaf": params["min_data_in_leaf"],
        "lambdarank_truncation_level": params["lambdarank_truncation_level"],
    }
    logger.info("LambdaRank train done — metrics=%s", metrics)
    return RankTrainResult(booster=booster, metrics=metrics, hyperparams=hyperparams)


def write_artifacts(result: RankTrainResult, *, output_dir: Path) -> RankTrainingArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = output_dir / "model.txt"
    result.booster.save_model(str(model_path))

    # KServe LGBServer (`kserve/lgbserver:v0.14`) only loads files ending
    # in ``.bst`` (see ``MODEL_EXTENSIONS = ".bst"`` in lgbserver source).
    # The byte content is identical to ``model.txt`` — LightGBM's text
    # format works for both. Writing both side-by-side lets the same
    # artifact_uri serve both the CLI / accuracy report (model.txt) and
    # the KServe Pod (model.bst) without an extra promote-time copy.
    bst_path = output_dir / "model.bst"
    result.booster.save_model(str(bst_path))

    (output_dir / "metrics.json").write_text(json.dumps(result.metrics, indent=2))

    importances = result.booster.feature_importance(importance_type="gain")
    fi_path = output_dir / "feature_importance.csv"
    with fi_path.open("w", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["feature", "gain"])
        for feat, imp in zip(FEATURE_COLS_RANKER, importances, strict=True):
            w.writerow([feat, float(imp)])

    logger.info("Wrote ranker artifacts to %s", output_dir)
    return RankTrainingArtifacts(artifacts_dir=output_dir, model_path=model_path)


def _copy_if_requested(source: Path, destination: str | None) -> None:
    if not destination:
        return
    target = Path(destination).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, target)


def _default_tracker_factory(settings: TrainSettings) -> TrackerFactory:
    def _build(run_id: str, workdir: Path) -> ExperimentTracker:
        return NullExperimentTracker()

    return _build


def run(
    *,
    dry_run: bool = False,
    save_to: str | None = None,
    window_days: int = TRAINING_WINDOW_DAYS,
    repository: RankerTrainingRepository | None = None,
    uploader: ArtifactUploader | None = None,
    tracker_factory: TrackerFactory | None = None,
    hyperparams_override: dict[str, object] | None = None,
    experiment_name: str | None = None,
    model_output_path: str | None = None,
    metrics_output_path: str | None = None,
    feature_importance_output_path: str | None = None,
) -> str:
    """Execute one LambdaRank training run. Returns the saved model URI or local path."""
    configure_logging()
    settings = TrainSettings()
    run_id = generate_run_id()
    started_at = datetime.now(timezone.utc)
    date_str = started_at.strftime("%Y-%m-%d")

    logger.info("Starting ranker run %s (dry_run=%s)", run_id, dry_run)

    if dry_run:
        train_df, test_df = synthetic_ranking_frames()
        logger.warning("dry-run: using synthetic LambdaRank data")
    else:
        repository = repository or create_rank_repository(settings)
        full = repository.fetch_training_rows(window_days=window_days)
        if full.empty:
            raise RuntimeError(
                f"No ranker training rows in the last {window_days} days. "
                "Publish /search + /feedback events before retraining."
            )
        train_df, test_df = split_by_request_id(full)
    logger.info("Fetched %d train / %d test rows", len(train_df), len(test_df))

    params = build_rank_params(
        num_leaves=settings.num_leaves,
        learning_rate=settings.learning_rate,
        feature_fraction=settings.feature_fraction,
        bagging_fraction=settings.bagging_fraction,
        bagging_freq=settings.bagging_freq,
        min_data_in_leaf=settings.min_data_in_leaf,
        lambdarank_truncation_level=settings.lambdarank_truncation_level,
    )
    if hyperparams_override:
        params.update(hyperparams_override)

    if experiment_name:
        os.environ["VERTEX_EXPERIMENT_NAME"] = experiment_name

    build_tracker = tracker_factory or _default_tracker_factory(settings)

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        output_dir = workdir / "artifacts"
        with build_tracker(run_id, workdir) as tracker:
            result = train(
                train_df=train_df,
                test_df=test_df,
                params=params,
                num_iterations=settings.num_iterations,
                early_stopping_rounds=settings.early_stopping_rounds,
            )
            tracker.log_metrics(result.metrics)

        artifacts = write_artifacts(result, output_dir=output_dir)

        _copy_if_requested(artifacts.model_path, model_output_path)
        _copy_if_requested(output_dir / "metrics.json", metrics_output_path)
        _copy_if_requested(output_dir / "feature_importance.csv", feature_importance_output_path)

        if save_to:
            _copy_if_requested(artifacts.model_path, save_to)
            logger.info("Copied model.txt to %s", Path(save_to).expanduser())

        if dry_run:
            logger.warning("dry-run: skipping GCS upload + BQ insert")
            return str(save_to) if save_to else str(artifacts.model_path)

        assert repository is not None
        uploader = uploader or GcsArtifactUploader(bucket=settings.gcs_models_bucket)
        model_uri = uploader.upload(artifacts.artifacts_dir, run_id=run_id, date_str=date_str)
        logger.info("Uploaded artifacts; model URI: %s", model_uri)

        finished_at = datetime.now(timezone.utc)
        repository.save_run(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            model_path=model_uri,
            metrics=result.metrics,
            hyperparams=result.hyperparams,
            git_sha=os.getenv("GIT_SHA"),
            dataset_version=date_str,
        )
        logger.info("Ranker run %s complete: %s", run_id, model_uri)
        return model_uri


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LightGBM LambdaRank training job")
    parser.add_argument("--mode", choices=["job", "kfp"], default="job")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--save-to", default=None)
    parser.add_argument("--window-days", type=int, default=TRAINING_WINDOW_DAYS)
    parser.add_argument("--train-dataset-uri", default=None)
    parser.add_argument("--hyperparams-json", default=None)
    parser.add_argument("--experiment-name", default=None)
    parser.add_argument("--model-output-path", default=None)
    parser.add_argument("--metrics-output-path", default=None)
    parser.add_argument("--feature-importance-output-path", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        hyperparams_override = json.loads(args.hyperparams_json) if args.hyperparams_json else None
        if hyperparams_override is not None and not isinstance(hyperparams_override, dict):
            raise ValueError("--hyperparams-json must decode to an object")
        run(
            dry_run=args.dry_run,
            save_to=args.save_to,
            window_days=args.window_days,
            hyperparams_override=hyperparams_override,
            experiment_name=args.experiment_name,
            model_output_path=args.model_output_path,
            metrics_output_path=args.metrics_output_path,
            feature_importance_output_path=args.feature_importance_output_path,
        )
    except Exception:
        logger.exception("Ranker training job failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
