"""Apache Beam / Dataflow adapter for ``StreamProcessor``.

Phase 6 T2 — delegates to the existing ``ml/streaming/pipeline.py::run``
driver which guards apache-beam imports inside the function body so the
Port layer remains importable without the heavy dep.
"""

from __future__ import annotations

from ml.streaming.ports.stream_processor import StreamConfig, StreamProcessor


class DataflowStreamProcessor(StreamProcessor):
    def run(self, config: StreamConfig) -> str:
        # Lazy import: keeps apache-beam optional for unit tests / linting.
        from ml.streaming.pipeline import run as run_beam

        argv = [
            f"--runner={config.runner}",
            f"--project={config.project_id}",
            f"--region={config.region}",
            f"--input_topic={config.input_topic}",
            f"--output_table={config.output_table}",
            f"--window_size_sec={config.window_size_sec}",
        ]
        if config.temp_location:
            argv.append(f"--temp_location={config.temp_location}")
        if config.staging_location:
            argv.append(f"--staging_location={config.staging_location}")
        if config.streaming:
            argv.append("--streaming")
        run_beam(argv)
        return "submitted"
