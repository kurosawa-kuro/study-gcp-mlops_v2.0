"""Unit tests for scripts._common.resolve_project_id / PROJECT_ID env symmetry."""

from __future__ import annotations

import pytest

import scripts._common as common


def test_resolve_project_id_prefers_gcp_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GCP_PROJECT", "from-gcp")
    monkeypatch.setenv("PROJECT_ID", "from-makefile")
    assert common.resolve_project_id() == "from-gcp"


def test_resolve_project_id_falls_back_to_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.setenv("PROJECT_ID", "only-project-id")
    assert common.resolve_project_id() == "only-project-id"


def test_resolve_project_id_falls_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.delenv("PROJECT_ID", raising=False)
    monkeypatch.setattr(common, "DEFAULTS", {"PROJECT_ID": "yaml-default"})
    assert common.resolve_project_id() == "yaml-default"


def test_env_project_id_reads_gcp_project_when_project_id_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROJECT_ID", "")
    monkeypatch.setenv("GCP_PROJECT", "via-sibling")
    assert common.env("PROJECT_ID") == "via-sibling"


def test_env_gcp_project_reads_project_id_when_gcp_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.setenv("PROJECT_ID", "make-export")
    assert common.env("GCP_PROJECT") == "make-export"
