"""Phase 3 — LightGBM LambdaRank training job (CLI wrapper).

CLI: ``python -m pipeline.training_job.main``

ranking_log テーブルから学習データを構築する想定だが、Phase 3 初期 (seed 完了直後)
は ranking_log がほぼ空なので、``ml.training.trainer.run`` のフォールバック
(synthetic_ranking_frames) で動かす。

Phase 4 で BigQuery loader / Cloud Run Jobs に差し替える際、本ファイルが
trainer の orchestrator として残る (Phase 7 では KFP component から呼ばれる)。
"""

from __future__ import annotations

import os
from pathlib import Path

from ml.common import get_logger
from ml.common.config import TrainSettings
from ml.training.trainer import HyperParams, run

logger = get_logger("pipeline.training_job")


def main() -> None:
    settings = TrainSettings()
    artifacts_root = Path(os.environ.get("MODEL_ARTIFACTS_ROOT", settings.model_artifacts_root))
    if not artifacts_root.is_absolute():
        artifacts_root = Path("/app") / artifacts_root

    hp = HyperParams(
        num_leaves=settings.num_leaves,
        learning_rate=settings.learning_rate,
        num_boost_round=settings.num_boost_round,
        early_stopping_rounds=settings.early_stopping_rounds,
    )

    logger.info(
        "Phase 3 training_job start: artifacts_root=%s num_boost_round=%d",
        artifacts_root,
        hp.num_boost_round,
    )

    # Phase 3 初期は ranking_log が空 / 浅いので合成 fallback で確実に学習を一周させる。
    # Phase 4 以降で Postgres / BQ ranking_log を loader 経由で渡す。
    result = run(artifacts_root=artifacts_root, df=None, hp=hp)

    logger.info(
        "Phase 3 training_job done: run_id=%s metrics=%s train_rows=%d eval_rows=%d",
        result.run_id,
        result.metrics,
        result.num_train_rows,
        result.num_eval_rows,
    )


if __name__ == "__main__":
    main()
