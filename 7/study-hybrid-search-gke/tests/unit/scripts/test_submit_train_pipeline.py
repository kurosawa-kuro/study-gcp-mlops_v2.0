"""scripts.ops.submit_train_pipeline — env expansion + compile delegation (V5-8)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.ops import submit_train_pipeline


def test_main_requires_pipeline_root_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPELINE_ROOT_BUCKET", raising=False)
    monkeypatch.setenv("GCP_PROJECT", "p")

    import scripts._common as common

    orig_env = common.env

    def env_no_bucket(name: str, default: str | None = None) -> str:
        if name == "PIPELINE_ROOT_BUCKET":
            return ""
        return orig_env(name, default)

    monkeypatch.setattr("scripts.ops.submit_train_pipeline.env", env_no_bucket)
    assert submit_train_pipeline.main() == 1


def test_main_calls_compile_with_expanded_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GCP_PROJECT", "my-proj")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("PIPELINE_ROOT_BUCKET", "my-proj-pipeline-root")

    mock_main = MagicMock(return_value=0)
    monkeypatch.setattr("pipeline.workflow.compile.main", mock_main)

    old_argv = submit_train_pipeline.sys.argv[:]
    try:
        rc = submit_train_pipeline.main()
        built = list(submit_train_pipeline.sys.argv)
    finally:
        submit_train_pipeline.sys.argv = old_argv

    assert rc == 0
    mock_main.assert_called_once()
    assert "--project-id" in built and "my-proj" in built
    assert "--pipeline-root" in built and "gs://my-proj-pipeline-root/runs" in built
    assert "--output-dir" in built and "/tmp/pipelines" in built
