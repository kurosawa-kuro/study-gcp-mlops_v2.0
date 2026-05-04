"""Phase 3 — Evaluation job (NDCG@10 / MAP / Recall@20 の hold-out 再評価).

CLI: ``python -m pipeline.evaluation_job.main`` (latest model を読み込み)

ranking_log から hold-out split を作って LightGBM Booster で再評価し、
``ml/registry/artifacts/{run_id}/metrics.json`` を更新する。

Phase 3 初期は ranking_log が空なので、合成データで再評価する fallback を組む。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import lightgbm as lgb
import numpy as np

from ml.common import get_logger
from ml.data.feature_engineering import (
    FEATURE_COLS_RANKER,
    RANKER_GROUP_COL,
    RANKER_LABEL_COL,
)
from ml.evaluation.metrics import evaluate
from ml.training.model_builder import synthetic_ranking_frames

logger = get_logger("pipeline.evaluation_job")


def _resolve_latest_model(artifacts_root: Path) -> Path | None:
    latest = artifacts_root / "latest" / "model.lgb"
    if latest.exists():
        return latest
    for run_dir in (
        sorted(artifacts_root.iterdir(), reverse=True) if artifacts_root.exists() else []
    ):
        if run_dir.is_dir() and run_dir.name != "latest":
            candidate = run_dir / "model.lgb"
            if candidate.exists():
                return candidate
    return None


def main() -> None:
    artifacts_root = Path(os.environ.get("MODEL_ARTIFACTS_ROOT", "ml/registry/artifacts"))
    if not artifacts_root.is_absolute():
        artifacts_root = Path("/app") / artifacts_root

    model_path = _resolve_latest_model(artifacts_root)
    if model_path is None:
        logger.error("No model.lgb found under %s — run training first", artifacts_root)
        raise SystemExit(2)

    logger.info("evaluation_job start: model=%s", model_path)
    booster = lgb.Booster(model_file=str(model_path))

    # Phase 3 初期は ranking_log が空なので、synthetic eval split で評価する。
    # Phase 4 以降で Postgres ranking_log の hold-out window から取得する想定。
    _, eval_df = synthetic_ranking_frames(seed=42)
    eval_X = eval_df[FEATURE_COLS_RANKER].to_numpy(dtype=np.float64)
    eval_y = eval_df[RANKER_LABEL_COL].to_numpy(dtype=np.int32)
    eval_groups = eval_df.groupby(RANKER_GROUP_COL, sort=False).size().to_numpy()

    eval_preds = booster.predict(eval_X)
    metrics = evaluate(
        labels=eval_y,
        scores=np.asarray(eval_preds),
        groups=eval_groups,
        k_ndcg=10,
        k_recall=20,
    )

    # 既存 metrics.json を更新 (synthetic eval 結果を上書き保存)。
    metrics_json_path = model_path.parent / "metrics.json"
    existing = json.loads(metrics_json_path.read_text()) if metrics_json_path.exists() else {}
    existing["evaluation_metrics"] = {k: float(v) for k, v in metrics.items()}
    metrics_json_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))

    logger.info("evaluation_job done: metrics=%s", metrics)


if __name__ == "__main__":
    main()
