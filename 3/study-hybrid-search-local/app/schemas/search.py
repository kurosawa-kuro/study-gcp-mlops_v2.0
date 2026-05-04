"""Pydantic schemas for /search and /feedback endpoints.

Field naming mirrors the ranker feature vocabulary (snake_case, metric units
in column names where ambiguous) so there is zero translation between the
HTTP contract and ``FEATURE_COLS_RANKER`` / ``ranking_log.features``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    max_rent: int | None = Field(default=None, ge=0)
    layout: str | None = None
    max_walk_min: int | None = Field(default=None, ge=0)
    pet_ok: bool | None = None
    max_age: int | None = Field(default=None, ge=0)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int = Field(default=20, ge=1, le=100)


class SearchResultItem(BaseModel):
    property_id: str
    final_rank: int
    lexical_rank: int
    semantic_rank: int
    me5_score: float
    score: float | None = None  # None while rerank is disabled (Phase 4 MVP)
    # Phase 6 T4 — TreeSHAP attributions per ranker feature, populated only
    # when the caller sets ``/search?explain=true`` AND a reranker is wired
    # up. The ``_baseline`` key carries LightGBM's expected-value offset.
    attributions: dict[str, float] | None = None
    # Phase 6 T1 — auxiliary BQML popularity score. Populated only when
    # ``bqml_popularity_enabled=True`` AND the scorer returns a value for
    # this property. Separate from rerank ``score`` so the 10-column parity
    # invariant remains untouched.
    popularity_score: float | None = None
    # --- Display-side metadata (Phase 7 Run 6, additive) ----------------------
    # `properties_cleaned` から JOIN 取得した物件メタ。UI が「数字テーブル」
    # ではなく「物件カード」として描画するために必要。既存 API 呼び出し側に
    # 影響しないよう全 Optional (None でもレスポンス JSON から消える pydantic
    # default 挙動には依存していないので、None で出る点は ok)。
    title: str | None = None
    city: str | None = None
    ward: str | None = None
    layout: str | None = None
    rent: int | None = None
    walk_min: int | None = None
    age_years: int | None = None
    area_m2: float | None = None
    pet_ok: bool | None = None


class SearchResponse(BaseModel):
    request_id: str
    results: list[SearchResultItem]
    model_path: str | None = None


class FeedbackRequest(BaseModel):
    request_id: str
    property_id: str
    action: str = Field(..., pattern=r"^(click|favorite|inquiry)$")


class FeedbackResponse(BaseModel):
    accepted: bool
