"""Phase 6 T2 — Apache Beam streaming pipeline.

Reads the ``ranking-log`` Pub/Sub topic, tumbling-windows events into
1-hour buckets, aggregates (impressions, clicks) per ``property_id``, and
writes the result to ``mlops.ranking_log_hourly_ctr``. A separate
Dataflow job from the Phase 5 BQ Subscription raw sink.

Input payload shape (JSON, produced by
``app/services/adapters/candidate_retriever.py::PubSubRankingLogPublisher``)::

    {
      "request_id": "...",
      "ts": "2026-04-24T10:00:00+00:00",
      "property_id": "p001",
      "final_rank": 3,
      "score": 0.42,
      ...
    }

We currently synthesize "click" signals from ``final_rank == 1`` — the
top-ranked property in each request is treated as the clicked one. This
is a learning-scale proxy; production would join against real
``/feedback`` events via another Beam side input or a separate pipeline.

Run the pipeline (locally with DirectRunner, or on Dataflow)::

    python -m ml.streaming.pipeline \\
        --runner=DataflowRunner \\
        --project=mlops-dev-a \\
        --region=asia-northeast1 \\
        --temp_location=gs://mlops-dev-a-artifacts/tmp \\
        --staging_location=gs://mlops-dev-a-artifacts/staging \\
        --input_topic=projects/mlops-dev-a/topics/ranking-log \\
        --output_table=mlops-dev-a:mlops.ranking_log_hourly_ctr \\
        --window_size_sec=3600 \\
        --streaming

The module is intentionally importable without ``apache-beam`` installed
— the Beam-dependent code is guarded inside ``run()`` so ``ruff check``
and import boundary tests do not require the heavy dep.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("ml.streaming.pipeline")


def _parse_event(payload: bytes) -> dict[str, Any] | None:
    """Decode + light-validate a ranking-log Pub/Sub payload."""
    try:
        event = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(event, dict):
        return None
    if "property_id" not in event or "ts" not in event:
        return None
    return event


def _event_timestamp_seconds(event: dict[str, Any]) -> float | None:
    """Convert ISO8601 ts to epoch seconds; return None on parse failure."""
    ts = event.get("ts")
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _to_kv(event: dict[str, Any]) -> tuple[str, tuple[int, int]]:
    """Project event to (property_id, (impressions, clicks)).

    ``final_rank == 1`` is treated as a click (coarse proxy; fine for
    learning, not for production SLO-grade CTR). Every event counts as
    one impression.
    """
    property_id = str(event["property_id"])
    final_rank = event.get("final_rank")
    click = 1 if isinstance(final_rank, int) and final_rank == 1 else 0
    return property_id, (1, click)


def _sum_pair(values: list[tuple[int, int]]) -> tuple[int, int]:
    impressions = sum(v[0] for v in values)
    clicks = sum(v[1] for v in values)
    return impressions, clicks


def _format_output_row(
    window_start_epoch: float,
    window_end_epoch: float,
    property_id: str,
    counts: tuple[int, int],
) -> dict[str, Any]:
    impressions, clicks = counts
    ctr = (clicks / impressions) if impressions else None
    return {
        "window_start": datetime.fromtimestamp(window_start_epoch, tz=timezone.utc).isoformat(),
        "window_end": datetime.fromtimestamp(window_end_epoch, tz=timezone.utc).isoformat(),
        "property_id": property_id,
        "impressions": int(impressions),
        "clicks": int(clicks),
        "ctr": ctr,
    }


def run(argv: list[str] | None = None) -> None:
    """Entry point. Imports apache-beam lazily so `import ml.streaming.pipeline`
    does not require the dep (keeps ruff / mypy happy on repos without Beam).
    """
    import apache_beam as beam
    from apache_beam import window
    from apache_beam.options.pipeline_options import PipelineOptions
    from apache_beam.transforms.combiners import Mean  # noqa: F401  (future use)

    parser = argparse.ArgumentParser()
    parser.add_argument("--input_topic", required=True)
    parser.add_argument("--output_table", required=True)
    parser.add_argument(
        "--window_size_sec",
        type=int,
        default=3600,
        help="Tumbling-window length in seconds (default 1h).",
    )
    known_args, beam_args = parser.parse_known_args(argv)
    options = PipelineOptions(beam_args, streaming=True, save_main_session=True)
    window_size = known_args.window_size_sec

    class _AttachWindowTimestamps(beam.DoFn):  # type: ignore[misc]
        def process(
            self,
            kv: tuple[str, tuple[int, int]],
            w: Any = beam.DoFn.WindowParam,
        ) -> Any:
            start_epoch = float(w.start)
            end_epoch = float(w.end)
            property_id, counts = kv
            yield _format_output_row(start_epoch, end_epoch, property_id, counts)

    class _CombineCountsFn(beam.CombineFn):  # type: ignore[misc]
        def create_accumulator(self) -> tuple[int, int]:
            return (0, 0)

        def add_input(self, acc: tuple[int, int], inp: tuple[int, int]) -> tuple[int, int]:
            return (acc[0] + inp[0], acc[1] + inp[1])

        def merge_accumulators(self, accumulators: Any) -> tuple[int, int]:
            imps, clks = 0, 0
            for a in accumulators:
                imps += a[0]
                clks += a[1]
            return (imps, clks)

        def extract_output(self, acc: tuple[int, int]) -> tuple[int, int]:
            return acc

    with beam.Pipeline(options=options) as pipeline:
        _ = (
            pipeline
            | "ReadFromPubSub" >> beam.io.ReadFromPubSub(topic=known_args.input_topic)
            | "DecodeAndFilter"
            >> beam.FlatMap(lambda b: [e for e in [_parse_event(b)] if e is not None])
            | "WithTimestamp"
            >> beam.Map(
                lambda e: beam.window.TimestampedValue(e, _event_timestamp_seconds(e) or 0.0)
            )
            | "ToKV" >> beam.Map(_to_kv)
            | "TumblingWindow" >> beam.WindowInto(window.FixedWindows(window_size))
            | "CombinePerProperty" >> beam.CombinePerKey(_CombineCountsFn())
            | "AttachWindow" >> beam.ParDo(_AttachWindowTimestamps())
            | "WriteToBQ"
            >> beam.io.WriteToBigQuery(
                table=known_args.output_table,
                schema=(
                    "window_start:TIMESTAMP,"
                    "window_end:TIMESTAMP,"
                    "property_id:STRING,"
                    "impressions:INT64,"
                    "clicks:INT64,"
                    "ctr:FLOAT"
                ),
                write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
                create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                method="STREAMING_INSERTS",
            )
        )


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    run()
