"""KServe HTTP-backed ``PredictorService`` adapter.

Thin wrapper around the v1/v2 KServe inference protocol used for offline
batch scoring (``pipeline/batch_serving_job``). The interactive /search
path uses the more specific ``KServeEncoder`` / ``KServeReranker``
adapters in ``app/services/adapters/``.
"""

from __future__ import annotations

from typing import Any

import httpx

from ml.serving.ports.predictor_service import PredictorService


class KServePredictorAdapter(PredictorService):
    def __init__(
        self,
        *,
        endpoint_url: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._timeout_seconds = timeout_seconds

    def predict(self, instances: list[object]) -> list[object]:
        payload: dict[str, Any] = {"instances": instances}
        with httpx.Client(timeout=self._timeout_seconds) as client:
            resp = client.post(self._endpoint_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        predictions = data.get("predictions") or data.get("outputs") or []
        if not isinstance(predictions, list):
            raise ValueError(f"unexpected predictions shape: {type(predictions)!r}")
        return predictions

    def predict_with_explain(
        self,
        instances: list[object],
        feature_names: list[str] | None = None,
    ) -> tuple[list[object], list[dict[str, float]]]:
        # Generic Port has no shared explain protocol across model families.
        # Encoder/Reranker-specific explain lives in app/services/adapters/.
        raise NotImplementedError(
            "predict_with_explain is search-specific; use KServeReranker instead"
        )
