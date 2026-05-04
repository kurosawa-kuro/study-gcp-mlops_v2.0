"""Recorded-call ``RerankerClient`` stub with deterministic scores."""

from __future__ import annotations


class MockRerankerClient:
    """Returns predictable descending scores; records every call.

    Default behaviour: ``predict([row1, row2, row3])`` → ``[1.0, 0.9, 0.8, ...]``
    so ranking tests can assert order without computing LightGBM math.

    For Phase 6 T4 (explain) tests, ``predict_with_explain`` returns a
    flat ``1/N`` attribution per feature plus ``_baseline`` so the
    ``RerankerExplainer`` Protocol is satisfied.
    """

    def __init__(
        self,
        *,
        score_fn: object | None = None,
        model_path: str = "stub-reranker",
    ) -> None:
        # ``score_fn`` lets tests inject custom scoring; default is the
        # 1.0/0.9/0.8/... staircase. Stored as ``object`` to keep the
        # adapter Protocol structural at runtime.
        self._score_fn = score_fn
        self.model_path = model_path
        self.endpoint_name = "stub-reranker"
        self.predict_calls: list[list[list[float]]] = []
        self.explain_calls: list[tuple[list[list[float]], list[str]]] = []

    def _scores(self, instances: list[list[float]]) -> list[float]:
        if self._score_fn is None:
            return [1.0 - 0.1 * i for i in range(len(instances))]
        scores = self._score_fn(instances)  # type: ignore[operator]
        return [float(s) for s in scores]

    def predict(self, instances: list[list[float]]) -> list[float]:
        self.predict_calls.append([list(row) for row in instances])
        return self._scores(instances)

    def predict_with_explain(
        self,
        instances: list[list[float]],
        feature_names: list[str],
    ) -> tuple[list[float], list[dict[str, float]]]:
        self.explain_calls.append(([list(row) for row in instances], list(feature_names)))
        scores = self._scores(instances)
        per_feature_attr = 1.0 / max(1, len(feature_names))
        attributions = [
            {**{name: per_feature_attr for name in feature_names}, "_baseline": 0.0}
            for _ in instances
        ]
        return scores, attributions
