"""``PipelineComponent`` Port — abstract pipeline task.

A component is a unit of work in a DAG (load features, train, evaluate,
register). The Port is intentionally minimal — implementations decide
how the runtime task is materialized (KFP ``@dsl.component``, Airflow
``Operator``, etc.).
"""

from __future__ import annotations

from typing import Any, Protocol


class PipelineComponent(Protocol):
    """One DAG node."""

    @property
    def name(self) -> str: ...

    def to_runtime_task(self, config: dict[str, Any]) -> Any:
        """Materialize the component into the runtime's task type."""
        ...


class PipelineComponentRef(Protocol):
    """Reference returned after adding a component to an orchestrator.

    Used by ``PipelineOrchestrator.add_dependency`` to connect tasks. The
    runtime concrete type is opaque to the Port consumer.
    """

    @property
    def name(self) -> str: ...
