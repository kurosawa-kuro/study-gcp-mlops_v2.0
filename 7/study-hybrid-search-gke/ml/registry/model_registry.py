"""Vertex AI Model Registry wrapper.

登録済みモデルをシンボリックにプロモートするためのラッパ。
実体は `pipeline/training_job/components/register_reranker.py` の KFP コンポーネ
ントで Vertex Model アップロードを行うため、ここでは CLI / 運用スクリプトから
呼び出される薄いインタフェースのみを提供する。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegisteredModel:
    """Vertex AI Model Registry entry."""

    project: str
    location: str
    model_id: str
    display_name: str
    version_id: str
    artifact_uri: str


class ModelRegistry:
    """Thin facade over ``google.cloud.aiplatform`` for model promotion."""

    def __init__(self, *, project: str, location: str) -> None:
        self._project = project
        self._location = location

    def promote(self, *, model_id: str, version_id: str, alias: str = "default") -> None:
        """Promote ``(model_id, version_id)`` to ``alias`` (default / production)."""
        from google.cloud import aiplatform

        aiplatform.init(project=self._project, location=self._location)
        model = aiplatform.Model(model_name=model_id)
        model.add_version_aliases(new_aliases=[alias], version=version_id)  # type: ignore[attr-defined]
