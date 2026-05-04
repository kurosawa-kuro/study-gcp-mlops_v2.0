"""``RankerModel`` Port — abstract trained ranker.

Wrap a fitted booster (LightGBM / XGBoost / etc.) so the rest of the
codebase (evaluation, KServe container, registration scripts) can score
candidates without the SDK type leaking through.
"""

from __future__ import annotations

from typing import Protocol


class RankerModel(Protocol):
    """Trained ranker — single source of truth for prediction + persistence.

    Implementations:
    - ``ml/training/adapters/lightgbm_trainer.py::LightGBMModel``
      wraps a ``lgb.Booster``.
    """

    def predict(self, features: list[list[float]]) -> list[float]:
        """Return one score per row in the feature matrix."""
        ...

    def predict_with_explain(
        self,
        features: list[list[float]],
        feature_names: list[str],
    ) -> tuple[list[float], list[dict[str, float]]]:
        """Return scores plus per-feature TreeSHAP attributions (Phase 6 T4)."""
        ...

    def save(self, path: str) -> None:
        """Persist the underlying model artifact to a local path."""
        ...
