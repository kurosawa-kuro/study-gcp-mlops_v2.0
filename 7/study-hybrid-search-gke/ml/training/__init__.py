"""Training layer: LightGBM LambdaRank trainer, dataset builders, experiments."""

from .model_builder import split_by_request_id, synthetic_ranking_frames
from .trainer import (
    RankTrainingArtifacts,
    RankTrainResult,
    build_rank_params,
    run,
    train,
    write_artifacts,
)

__all__ = [
    "RankTrainResult",
    "RankTrainingArtifacts",
    "build_rank_params",
    "run",
    "split_by_request_id",
    "synthetic_ranking_frames",
    "train",
    "write_artifacts",
]
