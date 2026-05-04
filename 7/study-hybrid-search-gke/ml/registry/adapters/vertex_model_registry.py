"""Vertex AI Model Registry adapter implementing ``ModelRegistryPort``.

Wraps ``google.cloud.aiplatform`` so callers (deploy scripts, training
pipeline components) only depend on the Port. The existing
``ml/registry/model_registry.py::ModelRegistry`` thin facade is retained
for legacy callers; new code should consume this adapter via the Port.
"""

from __future__ import annotations

from ml.registry.ports.model_registry import ModelRegistryPort, RegisteredModelRef


class VertexModelRegistryAdapter(ModelRegistryPort):
    def __init__(self, *, project: str, location: str) -> None:
        self._project = project
        self._location = location

    # ------------------------------------------------------------------ helpers

    def _init(self) -> None:
        from google.cloud import aiplatform  # lazy

        aiplatform.init(project=self._project, location=self._location)

    # ------------------------------------------------------------------ Port impl

    def register(
        self,
        *,
        display_name: str,
        artifact_uri: str,
        labels: dict[str, str] | None = None,
    ) -> RegisteredModelRef:
        from google.cloud import aiplatform

        self._init()
        model = aiplatform.Model.upload(
            display_name=display_name,
            artifact_uri=artifact_uri,
            serving_container_image_uri=(
                "asia-northeast1-docker.pkg.dev/"
                + self._project
                + "/mlops/property-reranker:latest"
            ),
            labels=labels or {},
        )
        return RegisteredModelRef(
            model_id=str(model.resource_name),
            version_id=str(getattr(model, "version_id", "1")),
            artifact_uri=artifact_uri,
        )

    def promote(
        self,
        *,
        model_id: str,
        version_id: str,
        alias: str = "production",
    ) -> None:
        from google.cloud import aiplatform

        self._init()
        model = aiplatform.Model(model_name=model_id)
        model.add_version_aliases(  # type: ignore[attr-defined]
            new_aliases=[alias], version=version_id
        )

    def resolve_alias(
        self,
        *,
        model_id: str,
        alias: str = "production",
    ) -> RegisteredModelRef:
        from google.cloud import aiplatform

        self._init()
        model = aiplatform.Model(model_name=f"{model_id}@{alias}")
        return RegisteredModelRef(
            model_id=str(model.resource_name),
            version_id=str(getattr(model, "version_id", alias)),
            artifact_uri=str(model.uri),
        )
