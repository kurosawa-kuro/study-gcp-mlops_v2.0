"""Generic predictor facade (ランク / 埋め込み両対応の上位抽象).

Vertex AI Endpoints 経由で predictor を呼び出す CLI / スモークテスト向け。
ここでは呼び出し面だけを提供し、実際の model loading は
``ml.serving.encoder`` / ``ml.serving.reranker`` に委譲する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Predictor(Protocol):
    """Minimal predictor interface used by serving adapters."""

    def predict(self, instances: list[object]) -> list[object]: ...


@dataclass(frozen=True)
class RemotePredictorConfig:
    project_id: str
    location: str
    endpoint_id: str
    timeout_seconds: float = 30.0

    @property
    def endpoint_name(self) -> str:
        return f"projects/{self.project_id}/locations/{self.location}/endpoints/{self.endpoint_id}"
