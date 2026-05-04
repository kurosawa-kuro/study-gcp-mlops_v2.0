"""Unit tests for scripts.infra.terraform_lock."""

from __future__ import annotations

from scripts.infra.terraform_lock import (
    is_state_lock_error,
    parse_terraform_lock_id,
    should_auto_force_unlock,
)


def test_parse_lock_id_from_terraform_stderr() -> None:
    blob = """
[31m│[0m Error acquiring the state lock
Lock Info:
  ID:        1777812961721387
  Who:       ubuntu@host
"""
    assert parse_terraform_lock_id(blob) == "1777812961721387"


def test_is_state_lock_error() -> None:
    assert is_state_lock_error("Error acquiring the state lock") is True
    assert is_state_lock_error("random plan output") is False


def test_should_auto_force_unlock_aliases(monkeypatch) -> None:
    for name in (
        "TERRAFORM_STATE_FORCE_UNLOCK",
        "DESTROY_ALL_FORCE_UNLOCK",
        "DEPLOY_ALL_FORCE_UNLOCK",
    ):
        monkeypatch.delenv("TERRAFORM_STATE_FORCE_UNLOCK", raising=False)
        monkeypatch.delenv("DESTROY_ALL_FORCE_UNLOCK", raising=False)
        monkeypatch.delenv("DEPLOY_ALL_FORCE_UNLOCK", raising=False)
        monkeypatch.setenv(name, "1")
        assert should_auto_force_unlock() is True
    monkeypatch.delenv("TERRAFORM_STATE_FORCE_UNLOCK", raising=False)
    monkeypatch.delenv("DESTROY_ALL_FORCE_UNLOCK", raising=False)
    monkeypatch.delenv("DEPLOY_ALL_FORCE_UNLOCK", raising=False)
    assert should_auto_force_unlock() is False
