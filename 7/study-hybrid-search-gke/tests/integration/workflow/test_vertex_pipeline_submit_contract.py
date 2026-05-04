"""Phase 7 workflow contract — Vertex submit/wait use canonical project resolution.

Incident: ``wait_train_succeeded`` failed when only ``GCP_PROJECT`` was set
(Composer-injected) while scripts read ``PROJECT_ID`` alone. Pin that
``pipeline_wait`` / ``submit_train_pipeline`` call :func:`scripts._common.resolve_project_id`.
"""

from __future__ import annotations

from tests.integration.workflow.conftest import read_repo_file as _read


def test_pipeline_wait_resolves_project_via_common_helper() -> None:
    wait_py = _read("scripts/ops/vertex/pipeline_wait.py")
    assert "resolve_project_id()" in wait_py
    assert "from scripts._common import" in wait_py and "resolve_project_id" in wait_py


def test_submit_train_pipeline_resolves_project_via_common_helper() -> None:
    submit_py = _read("scripts/ops/submit_train_pipeline.py")
    assert "resolve_project_id()" in submit_py
    assert "from scripts._common import" in submit_py and "resolve_project_id" in submit_py


def test_common_documents_gcp_project_precedence_in_resolve_project_id() -> None:
    """Docstring is the operator contract when debugging Composer/K8s env."""
    common_py = _read("scripts/_common.py")
    start = common_py.index("def resolve_project_id()")
    end = common_py.index("\ndef env(", start)
    block = common_py[start:end]
    assert "GCP_PROJECT" in block
    assert "Precedence" in block or "first non-empty" in block
