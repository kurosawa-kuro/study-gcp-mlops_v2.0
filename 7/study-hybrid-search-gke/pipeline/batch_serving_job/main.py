"""Batch serving job: offline re-rank of cached queries.

Placeholder KFP pipeline definition. The real implementation will:

1. Read a curated query set from ``mlops.popular_queries``.
2. Invoke the Vertex Batch Prediction API against the encoder + reranker
   endpoints.
3. Persist results into ``feature_mart.batch_search_results`` for cache hydration.
"""

from __future__ import annotations

import argparse
from typing import Any

from kfp import dsl

PIPELINE_NAME = "property-search-batch-serve"


@dsl.pipeline(
    name=PIPELINE_NAME, description="Offline batch prediction for popular hybrid-search queries."
)
def property_search_batch_serve_pipeline(
    project_id: str = "mlops-dev-a",
    vertex_location: str = "asia-northeast1",
) -> None:
    """Batch serving pipeline — TODO: wire real components."""
    del project_id, vertex_location


def get_pipeline() -> Any:
    return property_search_batch_serve_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="property-search-batch-serve pipeline CLI")
    parser.add_argument("action", choices=["compile", "submit"], default="compile", nargs="?")
    parser.parse_args(argv)
    print(f"[stub] {PIPELINE_NAME} pipeline compile not implemented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
