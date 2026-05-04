"""KFP / Vertex AI Pipelines adapter for ``PipelineOrchestrator``.

Wraps ``kfp.dsl`` + ``kfp.compiler.Compiler`` and submits via
``google.cloud.aiplatform.PipelineJob``. The existing ``@dsl.pipeline``
decorated function in ``pipeline/training_job/main.py`` can be migrated
to use this adapter incrementally; for now the adapter exposes the
machinery so new jobs can be authored Port-first.
"""

from __future__ import annotations

from typing import Any

from pipeline.training_job.ports.pipeline_component import (
    PipelineComponent,
    PipelineComponentRef,
)
from pipeline.training_job.ports.pipeline_orchestrator import (
    PipelineConfig,
    PipelineOrchestrator,
)


class _Ref(PipelineComponentRef):
    def __init__(self, name: str, task: Any) -> None:
        self._name = name
        self._task = task

    @property
    def name(self) -> str:
        return self._name

    @property
    def task(self) -> Any:
        return self._task


class KFPOrchestrator(PipelineOrchestrator):
    def __init__(self, *, pipeline_name: str) -> None:
        self._pipeline_name = pipeline_name
        self._components: list[tuple[PipelineComponent, _Ref | None]] = []
        self._dependencies: list[tuple[str, str]] = []

    def add_component(self, component: PipelineComponent) -> PipelineComponentRef:
        ref = _Ref(component.name, task=None)
        self._components.append((component, ref))
        return ref

    def add_dependency(
        self,
        upstream: PipelineComponentRef,
        downstream: PipelineComponentRef,
    ) -> None:
        self._dependencies.append((upstream.name, downstream.name))

    def compile(self, *, output_path: str) -> str:
        # Lazy KFP imports keep the Port consumers (and unit tests) free
        # of the heavy dependency.
        from kfp import compiler, dsl

        components = list(self._components)
        deps = list(self._dependencies)

        @dsl.pipeline(name=self._pipeline_name)
        def _pipeline_fn() -> None:
            tasks: dict[str, Any] = {}
            for component, _ref in components:
                tasks[component.name] = component.to_runtime_task({})
            for upstream_name, downstream_name in deps:
                tasks[downstream_name].after(tasks[upstream_name])

        compiler.Compiler().compile(pipeline_func=_pipeline_fn, package_path=output_path)
        return output_path

    def submit(self, *, config: PipelineConfig) -> str:
        from google.cloud import aiplatform

        aiplatform.init(project=config.project_id, location=config.location)
        job = aiplatform.PipelineJob(
            display_name=config.pipeline_name,
            template_path=f"{config.pipeline_root}/{config.pipeline_name}.yaml",
            parameter_values=dict(config.parameters),
            pipeline_root=config.pipeline_root,
        )
        job.submit()
        return str(job.resource_name)
