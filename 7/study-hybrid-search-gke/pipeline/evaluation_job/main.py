"""Evaluation job: gate the latest trained model against offline metrics.

Placeholder KFP pipeline definition. The real implementation will:

1. Load the latest ``mlops.training_runs`` row + held-out evaluation frame.
2. Re-compute NDCG@10 / MAP / Recall@20 via :mod:`ml.evaluation.metrics`.
3. Compare against the current production version and publish a gating
   decision (pass/fail) to ``mlops.validation_results``.
"""

from __future__ import annotations

import argparse
from typing import Any

from kfp import dsl

PIPELINE_NAME = "property-search-evaluate"


@dsl.pipeline(name=PIPELINE_NAME, description="Offline evaluation of the latest reranker.")
def property_search_evaluate_pipeline(
    project_id: str = "mlops-dev-a",
    vertex_location: str = "asia-northeast1",
    gate_metric_name: str = "ndcg_at_10",
    gate_threshold: float = 0.6,
) -> None:
    """Evaluation pipeline — TODO: wire real components."""
    del project_id, vertex_location, gate_metric_name, gate_threshold


def get_pipeline() -> Any:
    return property_search_evaluate_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="property-search-evaluate pipeline CLI")
    parser.add_argument("action", choices=["compile", "submit"], default="compile", nargs="?")
    parser.parse_args(argv)
    print(f"[stub] {PIPELINE_NAME} pipeline compile not implemented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
