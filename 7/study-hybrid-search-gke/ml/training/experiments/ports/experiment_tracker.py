"""Port for experiment tracking (Vertex Experiments / Null adapter).

Context-manager semantics so callers can ``with tracker: ...``; the enter
returns the tracker itself for chaining ``log_metrics``. Concrete adapter:
:class:`ml.training.experiments.adapters.null_tracker.NullExperimentTracker`.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol


class ExperimentTracker(Protocol):
    def __enter__(self) -> ExperimentTracker: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def log_metrics(self, metrics: dict[str, float]) -> None: ...
    def log_params(self, params: dict[str, object]) -> None: ...
