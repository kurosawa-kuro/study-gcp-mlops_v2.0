"""``StreamProcessor`` Port — streaming pipeline abstraction.

Currently backed by Apache Beam / Dataflow (``ranking-log`` Pub/Sub →
``ranking_log_hourly_ctr`` BigQuery table). Adapters could later
substitute Spark Structured Streaming or Flink without changing the
caller (``scripts/`` deployment driver, ``pipeline/data_job``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StreamConfig:
    project_id: str
    region: str
    input_topic: str
    output_table: str
    window_size_sec: int = 3600
    runner: str = "DataflowRunner"
    temp_location: str = ""
    staging_location: str = ""
    streaming: bool = True


class StreamProcessor(Protocol):
    def run(self, config: StreamConfig) -> str:
        """Submit / launch the streaming pipeline; returns a job-id-ish handle."""
        ...
