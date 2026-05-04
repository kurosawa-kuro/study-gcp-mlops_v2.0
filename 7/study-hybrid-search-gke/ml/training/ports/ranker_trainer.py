"""``RankerTrainer`` Port — abstract training engine.

Decouples ``ml/training/trainer.py::run`` orchestration from the
underlying booster library. Default implementation is LightGBM
LambdaRank (parity invariant; see ``CLAUDE.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ml.training.ports.ranker_model import RankerModel


@dataclass(frozen=True)
class TrainingResult:
    model: RankerModel
    metrics: dict[str, float]
    hyperparams: dict[str, object]


class RankerTrainer(Protocol):
    """Fit a ranker over (features, labels, query-grouped) input.

    ``train_groups`` carries the LambdaRank-style group sizes (number of
    candidates per query). Implementations must respect the order: the
    i-th group covers the next ``train_groups[i]`` rows of
    ``train_features`` / ``train_labels``.
    """

    def train(
        self,
        *,
        train_features: list[list[float]],
        train_labels: list[float],
        train_groups: list[int],
        test_features: list[list[float]],
        test_labels: list[float],
        test_groups: list[int],
        feature_names: list[str],
        params: dict[str, object],
    ) -> TrainingResult: ...
