"""Phase 3 — Training layer: LightGBM LambdaRank trainer + dataset builders."""

from .model_builder import split_by_request_id, synthetic_ranking_frames
from .trainer import HyperParams, TrainingResult, run, train, write_artifacts

__all__ = [
    "HyperParams",
    "TrainingResult",
    "run",
    "split_by_request_id",
    "synthetic_ranking_frames",
    "train",
    "write_artifacts",
]
