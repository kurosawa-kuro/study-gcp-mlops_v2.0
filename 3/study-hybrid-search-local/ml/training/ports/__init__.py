"""Ports for the ml/training feature.

Per [`docs/conventions/フォルダ-ファイル.md`](../../../docs/conventions/フォルダ-ファイル.md), Port-Adapter
boundaries live **inside** each ml/<feature> directory rather than at
``ml/`` root. This package owns the abstract training contract; the
concrete LightGBM implementation lives in ``ml/training/adapters/``.
"""

from .ranker_model import RankerModel
from .ranker_trainer import RankerTrainer, TrainingResult

__all__ = ["RankerModel", "RankerTrainer", "TrainingResult"]
