"""Pin the B17 Meilisearch + Cloud Run IAM auth-header contract.

The Phase 7 Run 1 lexical_search.py adapter (B17) split master_key onto
``Authorization`` and OIDC onto ``X-Serverless-Authorization`` to stop
Cloud Run IAM from validating-and-stripping the master key. The
``scripts/ops/sync_meili.py`` CLI must follow the same contract or the
Cloud Run-fronted Meilisearch will return 403 on every batch upsert.

Older code emitted ``x-meili-api-key`` (Meili v0 header) which v1.x no
longer supports — these tests guard the new contract so a future
"simplification" doesn't put us back in the 403 loop.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from scripts.ops.sync_meili import _headers


def _stub_id_token(_request: Any, _audience: str) -> str:
    return "fake-oidc-token"


def test_master_key_goes_on_authorization_header() -> None:
    with patch("scripts.ops.sync_meili.id_token.fetch_id_token", side_effect=_stub_id_token):
        h = _headers(
            base_url="https://meili-search-xxxx-an.a.run.app",
            api_key="my-master-key",
            require_identity_token=False,
        )
    assert h["authorization"] == "Bearer my-master-key"
    # v0 header must NOT appear (deprecated, ignored by Meili v1.x).
    assert "x-meili-api-key" not in h


def test_oidc_goes_on_x_serverless_authorization_when_required() -> None:
    with patch("scripts.ops.sync_meili.id_token.fetch_id_token", side_effect=_stub_id_token):
        h = _headers(
            base_url="https://meili-search-xxxx-an.a.run.app",
            api_key="my-master-key",
            require_identity_token=True,
        )
    # Master key stays on Authorization (Meili expects it there).
    assert h["authorization"] == "Bearer my-master-key"
    # OIDC token (Cloud Run IAM) lives on the alternate header so it
    # doesn't override the master key.
    assert h["x-serverless-authorization"] == "Bearer fake-oidc-token"


def test_no_oidc_when_not_required() -> None:
    h = _headers(
        base_url="https://meili-search-xxxx-an.a.run.app",
        api_key="my-master-key",
        require_identity_token=False,
    )
    assert "x-serverless-authorization" not in h


def test_no_api_key_means_no_authorization() -> None:
    """Anonymous Meili (no master key) must not set Authorization."""
    h = _headers(
        base_url="https://meili-search-xxxx-an.a.run.app",
        api_key="",
        require_identity_token=False,
    )
    assert "authorization" not in h
    assert "x-meili-api-key" not in h
