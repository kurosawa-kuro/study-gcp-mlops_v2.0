"""Phase C-5 — exercises the ``KFPOrchestrator`` adapter via stub components.

Skips if kfp is not installed (Beam/KFP are optional runtime deps; the
Port-level Protocol stays importable regardless).
"""

from __future__ import annotations

import pytest

pytest.importorskip("kfp")

from pipeline.training_job.adapters import KFPOrchestrator
from pipeline.training_job.ports import (
    PipelineComponent,
    PipelineComponentRef,
    PipelineOrchestrator,
)


class _StubComponent(PipelineComponent):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def to_runtime_task(self, config: dict[str, object]) -> object:
        # Returning a placeholder is enough — the real KFP graph compile is
        # exercised by integration tests against the actual components.
        return object()


def test_kfp_orchestrator_satisfies_protocol() -> None:
    orch: PipelineOrchestrator = KFPOrchestrator(pipeline_name="unit-test-pipeline")

    upstream: PipelineComponentRef = orch.add_component(_StubComponent("load"))
    downstream: PipelineComponentRef = orch.add_component(_StubComponent("train"))
    orch.add_dependency(upstream, downstream)

    assert upstream.name == "load"
    assert downstream.name == "train"
