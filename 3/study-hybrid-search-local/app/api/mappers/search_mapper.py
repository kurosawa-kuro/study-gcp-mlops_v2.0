"""Pydantic ↔ domain converters for /search.

The HTTP layer speaks Pydantic (``app.schemas``), the service layer speaks
domain models (``app.domain``). These functions are the only place the
two vocabularies meet.
"""

from __future__ import annotations

from app.domain.search import (
    SearchFilters,
    SearchInput,
    SearchOutput,
    SearchResultItem,
)
from app.schemas.search import (
    SearchRequest,
    SearchResponse,
)
from app.schemas.search import (
    SearchResultItem as SchemaSearchResultItem,
)


def _filters_from_pydantic(raw: dict[str, object]) -> SearchFilters:
    """Coerce a Pydantic ``SearchFilters.model_dump()`` dict to TypedDict.

    Skips ``None`` so ``total=False`` semantics hold (absent key ≠ None).
    """
    out: SearchFilters = {}
    max_rent = raw.get("max_rent")
    if isinstance(max_rent, int):
        out["max_rent"] = max_rent
    layout = raw.get("layout")
    if isinstance(layout, str):
        out["layout"] = layout
    max_walk_min = raw.get("max_walk_min")
    if isinstance(max_walk_min, int):
        out["max_walk_min"] = max_walk_min
    pet_ok = raw.get("pet_ok")
    if isinstance(pet_ok, bool):
        out["pet_ok"] = pet_ok
    max_age = raw.get("max_age")
    if isinstance(max_age, int):
        out["max_age"] = max_age
    return out


def search_request_to_input(
    req: SearchRequest,
    *,
    explain: bool = False,
) -> SearchInput:
    return SearchInput(
        query=req.query,
        filters=_filters_from_pydantic(req.filters.model_dump()),
        top_k=req.top_k,
        explain=explain,
    )


def search_result_item_to_schema(item: SearchResultItem) -> SchemaSearchResultItem:
    return SchemaSearchResultItem(
        property_id=item.property_id,
        final_rank=item.final_rank,
        lexical_rank=item.lexical_rank,
        semantic_rank=item.semantic_rank,
        me5_score=item.me5_score,
        score=item.score,
        attributions=item.attributions,
        popularity_score=item.popularity_score,
        title=item.title,
        city=item.city,
        ward=item.ward,
        layout=item.layout,
        rent=item.rent,
        walk_min=item.walk_min,
        age_years=item.age_years,
        area_m2=item.area_m2,
        pet_ok=item.pet_ok,
    )


def to_search_response(output: SearchOutput) -> SearchResponse:
    return SearchResponse(
        request_id=output.request_id,
        results=[search_result_item_to_schema(it) for it in output.items],
        model_path=output.model_path,
    )
