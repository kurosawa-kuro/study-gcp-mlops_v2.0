"""Ports for ``pipeline/training_job`` (canonical location).

Phase C-5 introduced ``PipelineOrchestrator`` here as the canonical
orchestration abstraction. The other ``pipeline/<verb>_job/ports/``
packages re-export from this module so all four jobs share one
Protocol surface (consolidation under ``pipeline/_common/`` is left for
a follow-up — see ``docs/02_移行ロードマップ-Port-Adapter-DI.md`` Phase C-5).
"""

from .pipeline_component import PipelineComponent, PipelineComponentRef
from .pipeline_orchestrator import PipelineConfig, PipelineOrchestrator

__all__ = [
    "PipelineComponent",
    "PipelineComponentRef",
    "PipelineConfig",
    "PipelineOrchestrator",
]
