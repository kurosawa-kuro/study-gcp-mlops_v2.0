"""Port for reranker inference providers."""

from __future__ import annotations

from typing import Protocol


class RerankerClient(Protocol):
    """Scores one batch of ranker-feature rows."""

    def predict(self, instances: list[list[float]]) -> list[float]: ...


class RerankerExplainer(Protocol):
    """Returns per-instance feature attributions alongside the scores.

    Phase 6 T4 — Explainable AI. Separate Protocol (not an extension of
    ``RerankerClient``) so services that never ask for explanations stay
    independent of explain-path typing.
    """

    def predict_with_explain(
        self,
        instances: list[list[float]],
        feature_names: list[str],
    ) -> tuple[list[float], list[dict[str, float]]]: ...
