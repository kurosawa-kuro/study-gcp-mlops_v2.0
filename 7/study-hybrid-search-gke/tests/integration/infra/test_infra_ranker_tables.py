"""Structural tests for the Phase 1 real-estate BigQuery tables.

These catch drift between the Terraform module and the documented contract in
``docs/tasks/TASKS_ROADMAP.md §5``:

* each new table exists in ``infra/terraform/modules/data/main.tf``,
* partitioning / clustering follow the roadmap (high-cardinality → cluster),
* ``training_runs.metrics`` carries both the legacy regression columns and
  the newly added ranker metrics (``ndcg_at_10`` / ``map`` / ``recall_at_20``),
* ``property_embeddings.embedding`` is ``FLOAT64 REPEATED`` (required for
  BigQuery VECTOR_SEARCH),
* ``ranking_log`` is clustered on ``request_id`` + ``property_id`` so the
  per-request offline eval query stays cheap.

Pure regex parsing so the test stays hermetic — no Terraform plan execution.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_PATH = REPO_ROOT / "infra" / "terraform" / "modules" / "data" / "main.tf"


def _read() -> str:
    return INFRA_PATH.read_text()


def _extract_resource_block(kind: str, name: str) -> str:
    pattern = re.compile(
        r'resource\s+"' + re.escape(kind) + r'"\s+"' + re.escape(name) + r'"\s*\{',
        re.MULTILINE,
    )
    text = _read()
    match = pattern.search(text)
    assert match, f"resource {kind}.{name} not found in {INFRA_PATH}"
    # walk braces to find the matching close
    depth = 1
    i = match.end()
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[match.start() : i]


# ---- New tables exist -------------------------------------------------------


def test_property_features_daily_declared() -> None:
    block = _extract_resource_block("google_bigquery_table", "property_features_daily")
    assert 'table_id            = "property_features_daily"' in block
    assert 'field = "event_date"' in block
    assert 'clustering = ["property_id"]' in block


def test_property_embeddings_declared_with_repeated_float64() -> None:
    block = _extract_resource_block("google_bigquery_table", "property_embeddings")
    # The REPEATED FLOAT64 column is the contract for BigQuery VECTOR_SEARCH.
    assert re.search(
        r'name\s*=\s*"embedding",\s*type\s*=\s*"FLOAT64",\s*mode\s*=\s*"REPEATED"',
        block,
    ), "property_embeddings.embedding must be FLOAT64 REPEATED"
    # 768d is documented in the roadmap — enforced via description at least.
    assert "768d" in block or "768" in block


def test_search_logs_declared() -> None:
    block = _extract_resource_block("google_bigquery_table", "search_logs")
    assert 'field = "ts"' in block
    assert 'clustering = ["request_id"]' in block
    # filters RECORD must carry all 5 filter keys used by SearchFilters pydantic.
    for key in ("max_rent", "layout", "max_walk_min", "pet_ok", "max_age"):
        assert f'"{key}"' in block, f"search_logs.filters.{key} missing"


def test_ranking_log_declared_with_dual_cluster() -> None:
    block = _extract_resource_block("google_bigquery_table", "ranking_log")
    assert 'field = "ts"' in block
    assert 'clustering = ["request_id", "property_id"]' in block, (
        "ranking_log must be clustered on request_id + property_id so per-request "
        "offline evaluation stays under scan quota."
    )
    for col in ("schema_version", "semantic_rank", "rrf_rank"):
        assert f'name = "{col}"' in block, f"ranking_log.{col} missing"
    assert 'name = "semantic_rank", type = "FLOAT64", mode = "NULLABLE"' in block


def test_feedback_events_declared() -> None:
    block = _extract_resource_block("google_bigquery_table", "feedback_events")
    assert 'field = "ts"' in block
    assert 'clustering = ["request_id", "property_id"]' in block


# ---- training_runs.metrics now carries both regression + ranker columns ----


def test_training_runs_metrics_has_ranker_columns() -> None:
    block = _extract_resource_block("google_bigquery_table", "training_runs")
    # Ranker columns are the live contract after Phase 10c.
    for ranker in ("ndcg_at_10", "map", "recall_at_20"):
        assert f'name = "{ranker}"' in block, f"ranker metrics.{ranker} missing"


def test_training_runs_hyperparams_has_lambdarank_fields() -> None:
    block = _extract_resource_block("google_bigquery_table", "training_runs")
    for field in ("min_data_in_leaf", "lambdarank_truncation_level"):
        assert f'name = "{field}"' in block, (
            f"hyperparams.{field} missing — required for the LambdaRank trainer"
        )


def test_legacy_predictions_log_removed() -> None:
    """Phase 10c guarantee — the California predictions_log no longer ships in Terraform."""
    text = _read()
    assert 'resource "google_bigquery_table" "predictions_log"' not in text, (
        "predictions_log must be deleted from Terraform (Phase 10c). "
        "Remaining references indicate the destructive migration is incomplete."
    )
