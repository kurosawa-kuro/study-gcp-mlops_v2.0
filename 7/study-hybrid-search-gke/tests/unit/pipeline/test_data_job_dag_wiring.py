"""Composition wiring for ``data_job`` DAG (Phase 7 PR-3).

Pin down the contract that ``vector_search_*`` parameters and the
``upsert_vector_search`` component are wired into the embed pipeline
spec, so silent regressions to the Strangler default fail at unit-test
time rather than at pipeline submit time.

NOTE on test strategy: ``pipeline.data_job.main`` cannot be imported
directly under KFP 2.16.0 due to a pre-existing (HEAD-reproducible)
``@dsl.pipeline`` validation error unrelated to PR-3. We therefore
verify the wiring via static inspection of ``main.py`` text — brittle
to formatting, robust to KFP version churn, and adequate for catching
the Strangler default regressions this test exists to guard.

Phase 7 ``docs/tasks/TASKS_ROADMAP.md`` §3.3 受け入れ条件 (ローカル):
- `ENABLE_VECTOR_SEARCH_UPSERT=false` で skip され、現行挙動と同等
"""

from __future__ import annotations

from pathlib import Path

MAIN_PATH = Path(__file__).resolve().parents[3] / "pipeline" / "data_job" / "main.py"


def _main_source() -> str:
    return MAIN_PATH.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------
# Pipeline parameter defaults (Strangler off)
# ----------------------------------------------------------------------------


def test_pipeline_signature_declares_strangler_off_defaults() -> None:
    """Pipeline function must default ``enable_vector_search_upsert=False``,
    ``vector_search_index_resource_name=""``, ``vector_search_upsert_batch_size=500``.
    """
    src = _main_source()
    assert "enable_vector_search_upsert: bool = False" in src
    assert 'vector_search_index_resource_name: str = ""' in src
    assert "vector_search_upsert_batch_size: int = 500" in src


# ----------------------------------------------------------------------------
# build_pipeline_spec contents (parameters + steps)
# ----------------------------------------------------------------------------


def test_build_pipeline_spec_lists_vector_search_params_with_strangler_defaults() -> None:
    """Spec exposed to operators / Cloud Function must echo the Strangler off defaults."""
    src = _main_source()
    assert '"enable_vector_search_upsert": False' in src
    assert '"vector_search_index_resource_name": ""' in src
    assert '"vector_search_upsert_batch_size": 500' in src


def test_build_pipeline_spec_steps_include_upsert_vector_search() -> None:
    src = _main_source()
    # Order: upsert must follow write_embeddings in the steps list (BQ MERGE first).
    write_idx = src.index('"write_embeddings"')
    upsert_idx = src.index('"upsert_vector_search"')
    assert write_idx < upsert_idx, (
        "upsert_vector_search must be listed AFTER write_embeddings so the "
        "BigQuery canonical store is written before the serving-side index."
    )


# ----------------------------------------------------------------------------
# Component wiring inside the pipeline body
# ----------------------------------------------------------------------------


def test_pipeline_body_invokes_upsert_vector_search() -> None:
    src = _main_source()
    assert "upsert_vector_search(" in src
    # Predictions output must flow from batch_predict_embeddings to the upsert step.
    assert 'predictions=predict_task.outputs["predictions"]' in src


def test_pipeline_imports_upsert_component() -> None:
    src = _main_source()
    assert "upsert_vector_search" in src.split("from pipeline.data_job.components import")[1]
