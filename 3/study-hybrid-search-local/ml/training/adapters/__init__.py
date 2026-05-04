"""Adapters implementing ``ml/training/ports``.

Phase C-1 introduced ``LightGBMRankerTrainer`` / ``LightGBMModel`` as
the default LambdaRank implementation; ``ml/training/trainer.py`` is
expected to consume these via the Port (refactor follow-up).
"""

from .lightgbm_trainer import LightGBMModel, LightGBMRankerTrainer

__all__ = ["LightGBMModel", "LightGBMRankerTrainer"]
