"""No-op :class:`ExperimentTracker` adapter.

Experiment logging in this phase is handled by BigQuery ``mlops.training_runs``
and Vertex AI Experiments via ``BigQueryRankerRepository.save_run``. The
trainer still depends on an ``ExperimentTracker`` object, so this null adapter
keeps the orchestration path simple without introducing any external tracker.
"""

from __future__ import annotations

from types import TracebackType


class NullExperimentTracker:
    """No-op experiment tracker with context-manager semantics."""

    def __enter__(self) -> NullExperimentTracker:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass

    def log_metrics(self, metrics: dict[str, float]) -> None:
        pass

    def log_params(self, params: dict[str, object]) -> None:
        pass
