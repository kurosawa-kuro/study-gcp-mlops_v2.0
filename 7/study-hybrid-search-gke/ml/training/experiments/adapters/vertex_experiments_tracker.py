"""Vertex AI Experiments adapter for ``ExperimentTracker``.

Run 3 で `ml/data/loaders/ranker_repository.py::BigQueryRankerRepository`
の `_log_vertex_experiment` 内に埋め込まれていた dual-write を adapter
として外出ししたもの。Repository の責務が「BQ への row insert + tracker
への delegate」に純化される。

設計メモ:

- `aiplatform.start_run(run=<run_id>, resume=True)` は context manager。
  本 adapter の `__enter__` で `aiplatform.init` + `start_run.__enter__` を
  まとめて呼び、`__exit__` で `start_run.__exit__` を伝搬させる。
- `aiplatform.log_params` / `log_metrics` は active run の存在を前提とする
  module-global API なので、本 adapter は `with` 文の内側だけで safe。
- `aiplatform` import は lazy (本番 cluster で本 module を import するだけで
  Vertex SDK 初期化が走るのを避けるため)。
- Repository から見ると `ExperimentTracker` Protocol を満たす差し替え可能な
  実装。Vertex SDK が使えない環境では `NullExperimentTracker` に fallback
  すれば呼び出し側のコードは無変更。
"""

from __future__ import annotations

from types import TracebackType
from typing import Any


class VertexExperimentsTracker:
    """``ExperimentTracker`` adapter that writes to Vertex AI Experiments.

    Args:
        project_id: GCP project id (passed to ``aiplatform.init``).
        experiment_name: Vertex Experiments name. Train pipeline /
            ``BigQueryRankerRepository`` reads ``VERTEX_EXPERIMENT_NAME`` env
            and constructs this adapter only when the value is non-empty.
        run_id: Identifier passed as ``aiplatform.start_run(run=...)``;
            ``resume=True`` so re-running a job with the same id appends
            params / metrics rather than failing.
    """

    def __init__(
        self,
        *,
        project_id: str,
        experiment_name: str,
        run_id: str,
    ) -> None:
        self._project_id = project_id
        self._experiment_name = experiment_name
        self._run_id = run_id
        self._run_handle: Any = None

    def __enter__(self) -> VertexExperimentsTracker:
        from google.cloud import aiplatform

        aiplatform.init(project=self._project_id, experiment=self._experiment_name)
        self._run_handle = aiplatform.start_run(run=self._run_id, resume=True)
        self._run_handle.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._run_handle is None:
            return
        try:
            self._run_handle.__exit__(exc_type, exc, tb)
        finally:
            self._run_handle = None

    def log_metrics(self, metrics: dict[str, float]) -> None:
        from google.cloud import aiplatform

        aiplatform.log_metrics(
            {key: float(value) for key, value in metrics.items() if isinstance(value, int | float)}
        )

    def log_params(self, params: dict[str, object]) -> None:
        from google.cloud import aiplatform

        aiplatform.log_params(
            {
                key: value
                for key, value in params.items()
                if isinstance(value, float | int | str) and value is not None
            }
        )
