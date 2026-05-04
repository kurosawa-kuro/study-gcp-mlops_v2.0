"""Phase 3 — Meilisearch (Docker) lexical adapter.

Phase 7 の ``MeilisearchLexical`` から GCP / Cloud Run Identity Token / impersonation
認証を全削除し、master key + Docker hostname (`http://meilisearch:7700`) のみで動く
シンプル版に書き直した。

Phase 4 で Meilisearch を Cloud Run に移すとき、この adapter を Phase 7 同等に
"足し算" し直す (Identity Token + impersonation 認証を再導入)。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.domain.retrieval import LexicalResult
from app.domain.search import SearchFilters
from app.services.protocols.lexical_search import LexicalSearchPort
from ml.common import get_logger


class MeilisearchLexicalSearch(LexicalSearchPort):
    """Calls Meilisearch ``/indexes/<index>/search`` and returns rank list."""

    def __init__(
        self,
        *,
        base_url: str,
        index_name: str = "properties",
        master_key: str = "",
        timeout_seconds: float = 3.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._index_name = index_name
        self._master_key = master_key
        self._timeout_seconds = timeout_seconds
        self._logger = get_logger("app.adapters.meilisearch_lexical")

    def search(
        self,
        *,
        query: str,
        filters: SearchFilters,
        top_k: int,
    ) -> list[LexicalResult]:
        headers: dict[str, str] = {"content-type": "application/json"}
        if self._master_key:
            headers["authorization"] = f"Bearer {self._master_key}"

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
