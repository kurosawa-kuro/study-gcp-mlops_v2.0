"""``PredictorService`` Port — generic remote-prediction interface.

Distinct from the per-Port ``EncoderClient`` / ``RerankerClient`` in
``app/services/protocols/``: those are search-API specific. This Port is
the generic shape for batch-serving and offline evaluation, where the
caller does not care whether the predictor is encoder or reranker.

Implementations: ``ml/serving/adapters/kserve_predictor.py``.
"""

from __future__ import annotations

from typing import Protocol


class PredictorService(Protocol):
    def predict(self, instances: list[object]) -> list[object]:
        """Send instances and return predictions in the same order."""
        ...

    def predict_with_explain(
        self,
        instances: list[object],
        feature_names: list[str] | None = None,
    ) -> tuple[list[object], list[dict[str, float]]]:
        """Optional Phase 6 T4 path. Implementations may raise NotImplementedError."""
        ...
