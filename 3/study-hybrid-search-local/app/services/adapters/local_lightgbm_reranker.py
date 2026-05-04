"""Phase 3 — Local LightGBM LambdaRank reranker (in-process).

Phase 7 では KServe InferenceService に rerank を委譲するが、Phase 3 では
LightGBM Booster を ``ml/registry/artifacts/{run_id}/model.lgb`` から直接 load し、
プロセス内で predict する。

Phase 4 で Cloud Run reranker サービスに差し替え可能。Port (`RerankerClient`) は
不変。
"""

from __future__ import annotations

import numpy as np

from app.services.protocols.reranker_client import RerankerClient
from ml.common import get_logger


class LocalLightGBMReranker(RerankerClient):
    """LightGBM Booster.predict by in-process call."""

    def __init__(self, *, model_path: str) -> None:
        # 遅延 import — test 環境で lightgbm が無い場合の import 失敗を回避。
        import lightgbm as lgb

        self._logger = get_logger("app.adapters.local_lightgbm_reranker")
        self._booster = lgb.Booster(model_file=model_path)
        self._model_path = model_path

    @property
    def model_path(self) -> str:
        return self._model_path

    def predict(self, instances: list[list[float]]) -> list[float]:
        if not instances:
            return []
        matrix = np.asarray(instances, dtype=np.float64)
        preds = self._booster.predict(matrix)
        return [float(x) for x in np.asarray(preds).ravel()]
