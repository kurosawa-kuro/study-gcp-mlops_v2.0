"""``PipelineOrchestrator`` Port — abstract DAG composition + submission.

Phase 7 default implementation is ``KFPOrchestrator`` (Vertex AI
Pipelines). Adapters could substitute Airflow / Kubeflow / Prefect
without changing the job-level ``main.py`` files that compose the DAG.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .pipeline_component import PipelineComponent, PipelineComponentRef


@dataclass(frozen=True)
class PipelineConfig:
    """Cross-runtime pipeline configuration."""

    project_id: str
    location: str
    pipeline_name: str
    pipeline_root: str
    parameters: dict[str, object] = field(default_factory=dict)


class PipelineOrchestrator(Protocol):
    def add_component(
        self,
        component: PipelineComponent,
    ) -> PipelineComponentRef:
        """Insert one task into the DAG; returns a reference for dependency wiring."""
        ...

    def add_dependency(
        self,
        upstream: PipelineComponentRef,
        downstream: PipelineComponentRef,
    ) -> None:
        """Force ``downstream`` to run after ``upstream`` completes."""
        ...

    def compile(self, *, output_path: str) -> str:
        """Compile the DAG to a runtime artifact (e.g. KFP YAML); return the path."""
        ...

    def submit(self, *, config: PipelineConfig) -> str:
        """Submit a compiled pipeline; return a runtime job identifier."""
        ...
