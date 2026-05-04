"""Pin the Phase 7 promote contract.

``deploy-kserve-models`` reads the ``production`` alias on each Vertex
Model; ``scripts/ops/promote.py`` is the canonical way to set that
alias. The Run 1 incident promoted a stale empty-URI version because
the original promote script had no guard; these tests pin the safety
nets (explicit version selection, empty-artifact_uri detection,
.bst rename) so a future refactor can't re-introduce the regression.
"""

from __future__ import annotations

import argparse
from typing import Any
from unittest.mock import patch

import pytest

from scripts.ops import promote as promote_mod


class _FakeRegistry:
    def __init__(self) -> None:
        self.added: list[tuple[list[str], str]] = []
        self.removed: list[tuple[list[str], str]] = []

    def add_version_aliases(self, *, new_aliases: list[str], version: str) -> None:
        self.added.append((list(new_aliases), str(version)))

    def remove_version_aliases(self, *, target_aliases: list[str], version: str) -> None:
        self.removed.append((list(target_aliases), str(version)))


class _FakeModel:
    def __init__(self, *, version_id: str, aliases: list[str], uri: str) -> None:
        self.version_id = version_id
        self.version_aliases = aliases
        self.uri = uri
        self.versioning_registry = _FakeRegistry()


def _args(**kwargs: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "model_kind": "reranker",
        "version_alias": None,
        "version_id": None,
        "model_id": None,
        "bst_rename": False,
        "apply": True,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_resolve_display_name_uses_model_not_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the Model vs Endpoint display_name distinction.

    Vertex *Models* are registered as ``property-{kind}`` (no ``-endpoint``
    suffix); Vertex *Endpoint* shells are ``property-{kind}-endpoint``.
    promote.py searches Models, so it must default to the no-suffix form.
    A regression that swaps these would make ``ops-promote-*`` silently
    return "no Model matched" against a populated registry.
    """
    monkeypatch.delenv("RERANKER_MODEL_DISPLAY_NAME", raising=False)
    monkeypatch.delenv("ENCODER_MODEL_DISPLAY_NAME", raising=False)
    assert promote_mod._resolve_display_name("reranker") == "property-reranker"
    assert promote_mod._resolve_display_name("encoder") == "property-encoder"


def test_resolve_display_name_env_override_uses_model_named_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The env override is named ``*_MODEL_DISPLAY_NAME`` (not ``*_ENDPOINT_*``).

    Phase 5/6 ops used ``RERANKER_ENDPOINT_DISPLAY_NAME`` which read the
    Endpoint display_name out of setting.yaml — pointed at a Model search
    that string returns zero hits. Renaming makes the contract explicit;
    this test pins it so we don't drift back.
    """
    monkeypatch.setenv("RERANKER_MODEL_DISPLAY_NAME", "custom-rr")
    monkeypatch.setenv("ENCODER_MODEL_DISPLAY_NAME", "custom-enc")
    assert promote_mod._resolve_display_name("reranker") == "custom-rr"
    assert promote_mod._resolve_display_name("encoder") == "custom-enc"


def test_select_version_picks_explicit_version_id() -> None:
    a = _FakeModel(version_id="1", aliases=["staging"], uri="gs://x/v1/")
    b = _FakeModel(version_id="2", aliases=["staging"], uri="gs://x/v2/")
    target = promote_mod._select_version([a, b], version_id="2", version_alias=None)
    assert target is b


def test_select_version_picks_alias() -> None:
    a = _FakeModel(version_id="1", aliases=["staging"], uri="gs://x/v1/")
    b = _FakeModel(version_id="2", aliases=["candidate"], uri="gs://x/v2/")
    target = promote_mod._select_version([a, b], version_id=None, version_alias="candidate")
    assert target is b


def test_select_version_errors_when_no_selector_matches() -> None:
    a = _FakeModel(version_id="1", aliases=["staging"], uri="gs://x/v1/")
    with pytest.raises(RuntimeError, match="no Model matched"):
        promote_mod._select_version([a], version_id="42", version_alias=None)


def test_set_production_alias_moves_alias_between_versions() -> None:
    a = _FakeModel(version_id="1", aliases=["production"], uri="gs://x/v1/")
    b = _FakeModel(version_id="2", aliases=["staging"], uri="gs://x/v2/")
    promote_mod._set_production_alias(b, [a, b], apply=True)
    assert a.versioning_registry.removed == [(["production"], "1")]
    assert b.versioning_registry.added == [(["production"], "2")]


def test_set_production_alias_dry_run_does_not_call_registry() -> None:
    a = _FakeModel(version_id="1", aliases=["production"], uri="gs://x/v1/")
    b = _FakeModel(version_id="2", aliases=[], uri="gs://x/v2/")
    promote_mod._set_production_alias(b, [a, b], apply=False)
    assert a.versioning_registry.removed == []
    assert b.versioning_registry.added == []


def test_run_alias_fails_fast_when_artifact_uri_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 7 Run 1 reranker/v1 regression: production alias was promoted
    to an artifact_uri that pointed to an empty bucket, causing a
    KServe Init:CrashLoopBackOff. The new promote refuses to apply
    when GCS lists 0 objects under the URI."""
    target = _FakeModel(version_id="1", aliases=["staging"], uri="gs://empty-bucket/v1/")
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setattr(promote_mod, "_list_versions", lambda _: [target])
    monkeypatch.setattr(promote_mod, "_gsutil_ls", lambda _uri: [])
    fake_aiplatform = type("M", (), {"init": staticmethod(lambda **_kw: None)})
    with (
        patch.dict("sys.modules", {"google.cloud.aiplatform": fake_aiplatform}),
        pytest.raises(RuntimeError, match="empty in GCS"),
    ):
        promote_mod._run_alias(_args(version_id="1"))


def test_run_alias_applies_when_artifact_uri_has_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _FakeModel(version_id="1", aliases=["staging"], uri="gs://bucket/v1/")
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setattr(promote_mod, "_list_versions", lambda _: [target])
    monkeypatch.setattr(promote_mod, "_gsutil_ls", lambda _uri: ["gs://bucket/v1/model.bst"])
    fake_aiplatform = type("M", (), {"init": staticmethod(lambda **_kw: None)})
    with patch.dict("sys.modules", {"google.cloud.aiplatform": fake_aiplatform}):
        result = promote_mod._run_alias(_args(version_id="1", apply=True))
    assert result["selected_version_id"] == "1"
    assert result["applied"] is True
    assert target.versioning_registry.added == [(["production"], "1")]


def test_bst_rename_no_op_when_bst_already_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        promote_mod,
        "_gsutil_ls",
        lambda _: ["gs://bucket/v1/model.bst", "gs://bucket/v1/model.txt"],
    )
    target_uri = promote_mod._bst_rename_if_needed("gs://bucket/v1/", apply=True)
    assert target_uri == "gs://bucket/v1/model.bst"


def test_bst_rename_plans_copy_in_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without --apply we should NOT shell out to gsutil cp."""
    monkeypatch.setattr(promote_mod, "_gsutil_ls", lambda _: ["gs://bucket/v1/model.txt"])

    def _fail_cp(*_args: Any, **_kw: Any) -> Any:
        raise AssertionError("gsutil cp must not run in dry mode")

    monkeypatch.setattr(promote_mod.subprocess, "run", _fail_cp)
    target_uri = promote_mod._bst_rename_if_needed("gs://bucket/v1/", apply=False)
    assert target_uri == "gs://bucket/v1/model.bst"


def test_bst_rename_returns_none_when_neither_file_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(promote_mod, "_gsutil_ls", lambda _: ["gs://bucket/v1/feature.csv"])
    assert promote_mod._bst_rename_if_needed("gs://bucket/v1/", apply=True) is None
