"""``ModelRegistryPort`` — abstract model registration / promotion.

Adapter: ``ml/registry/adapters/vertex_model_registry.py``. Used by
``scripts/deploy/kserve_models.py`` (resolve ``production`` alias →
artifact URI) and ``pipeline/training_job/components/register_reranker.py``
(register a freshly-trained model).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RegisteredModelRef:
    """Identifier triple for a registered model version."""

    model_id: str
    version_id: str
    artifact_uri: str


class ModelRegistryPort(Protocol):
    def register(
        self,
        *,
        display_name: str,
        artifact_uri: str,
        labels: dict[str, str] | None = None,
    ) -> RegisteredModelRef: ...

    def promote(
        self,
        *,
        model_id: str,
        version_id: str,
        alias: str = "production",
    ) -> None: ...

    def resolve_alias(
        self,
        *,
        model_id: str,
        alias: str = "production",
    ) -> RegisteredModelRef: ...
