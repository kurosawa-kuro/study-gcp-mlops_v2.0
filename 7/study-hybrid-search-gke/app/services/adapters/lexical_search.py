"""Production ``LexicalSearchPort`` adapter — Meilisearch.

Phase B-3 moved ``NoopLexicalSearch`` to ``app/services/noop_adapters/``. The
This is the only lexical adapter — Phase 7 dropped the Discovery Engine variant.
"""

from __future__ import annotations

import os
from typing import Any, cast

import httpx
from google.auth import default as google_auth_default
from google.auth import impersonated_credentials
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.domain.retrieval import LexicalResult
from app.domain.search import SearchFilters
from app.services.protocols.lexical_search import LexicalSearchPort
from ml.common import get_logger


class MeilisearchLexical(LexicalSearchPort):
    """Calls Meilisearch ``/indexes/properties/search`` and returns rank list."""

    def __init__(
        self,
        *,
        base_url: str,
        index_name: str = "properties",
        timeout_seconds: float = 3.0,
        api_key: str = "",
        require_identity_token: bool = True,
        impersonate_service_account: str = "",
        token_audience: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._index_name = index_name
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key
        self._require_identity_token = require_identity_token
        self._impersonate_service_account = impersonate_service_account.strip()
        self._token_audience = token_audience.strip()
        self._logger = get_logger("app")

    def _resolve_identity_token(self) -> str:
        preset = os.environ.get("MEILI_PRESIGNED_ID_TOKEN", "").strip()
        if preset:
            return preset

        audience = self._token_audience or self._base_url
        if self._impersonate_service_account:
            source_credentials, _ = google_auth_default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credentials_ctor: Any = impersonated_credentials.Credentials
            target_credentials = cast(
                Any,
                credentials_ctor(
                    source_credentials=source_credentials,
                    target_principal=self._impersonate_service_account,
                    target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    lifetime=600,
                ),
            )
            id_credentials_ctor: Any = impersonated_credentials.IDTokenCredentials
            id_credentials = cast(
                Any,
                id_credentials_ctor(
                    target_credentials,
                    target_audience=audience,
                    include_email=True,
                ),
            )
            id_credentials.refresh(Request())
            token = getattr(id_credentials, "token", "")
            if not token:
                raise RuntimeError(
                    "impersonated ID token refresh succeeded but no token was populated"
                )
            return str(token)

        return str(id_token.fetch_id_token(Request(), audience))  # type: ignore[no-untyped-call]

    def search(
        self,
        *,
        query: str,
        filters: SearchFilters,
        top_k: int,
    ) -> list[LexicalResult]:
        headers: dict[str, str] = {"content-type": "application/json"}
        # Meilisearch v1.x はマスターキーを `Authorization: Bearer` で要求するが、
        # Cloud Run も同じヘッダで OIDC token を要求するため衝突する。
        # Cloud Run は標準の `Authorization` を validate→strip するので、Meili 側に
        # マスターキーを届けるためには Cloud Run の代替ヘッダ
        # `X-Serverless-Authorization` を OIDC 用に使う必要がある (Cloud Run はこの
        # 別名でも IAM 認証を受け付けるドキュメント記載の代替)。
        # 参照: docs/runbook/05_運用.md / 動作検証結果.md Phase 7 Run 1 (B17)
        if self._require_identity_token:
            # Local PDCA dev: ``MEILI_PRESIGNED_ID_TOKEN`` で
            # ``gcloud auth print-identity-token`` の値を直接注入できる
            # (User OAuth は ``id_token.fetch_id_token`` (SA only) を通らない)。
            # Cloud Run Job / WI Pod では env 未設定で従来パスを使う。
            try:
                token = self._resolve_identity_token()
                headers["x-serverless-authorization"] = f"Bearer {token}"
            except Exception:
                self._logger.exception("Failed to mint ID token for meili-search")
                return []
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"

        payload: dict[str, Any] = {
            "q": query,
            "limit": top_k,
        }
        filter_expr = _to_meili_filter(filters)
        if filter_expr:
            payload["filter"] = filter_expr

        url = f"{self._base_url}/indexes/{self._index_name}/search"
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            self._logger.exception("Meilisearch request failed")
            return []

        hits = data.get("hits") or []
        out: list[LexicalResult] = []
        for idx, hit in enumerate(hits, start=1):
            property_id = str(hit.get("property_id") or "").strip()
            if not property_id:
                continue
            out.append(LexicalResult(property_id=property_id, rank=idx))
        return out


def _to_meili_filter(filters: SearchFilters) -> str | None:
    clauses: list[str] = []
    max_rent = filters.get("max_rent")
    if max_rent is not None:
        clauses.append(f"rent <= {int(max_rent)}")

    layout = filters.get("layout")
    if layout:
        escaped = str(layout).replace('"', '\\"')
        clauses.append(f'layout = "{escaped}"')

    max_walk_min = filters.get("max_walk_min")
    if max_walk_min is not None:
        clauses.append(f"walk_min <= {int(max_walk_min)}")

    pet_ok = filters.get("pet_ok")
    if pet_ok is not None:
        clauses.append(f"pet_ok = {'true' if bool(pet_ok) else 'false'}")

    max_age = filters.get("max_age")
    if max_age is not None:
        clauses.append(f"age_years <= {int(max_age)}")

    if not clauses:
        return None
    return " AND ".join(clauses)
