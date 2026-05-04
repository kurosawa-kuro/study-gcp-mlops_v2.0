"""Unit tests for ``app.api.mappers.search_mapper``."""

from __future__ import annotations

from app.api.mappers.search_mapper import (
    search_request_to_input,
    to_search_response,
)
from app.domain.search import SearchOutput, SearchResultItem
from app.schemas.search import SearchFilters as SchemaFilters
from app.schemas.search import SearchRequest


def test_search_request_to_input_propagates_filters_and_flags() -> None:
    req = SearchRequest(
        query="渋谷",
        filters=SchemaFilters(max_rent=200000, layout="1LDK", pet_ok=True),
        top_k=10,
    )
    domain = search_request_to_input(req, explain=True)

    assert domain.query == "渋谷"
    assert domain.top_k == 10
    assert domain.explain is True
    assert domain.filters.get("max_rent") == 200000
    assert domain.filters.get("layout") == "1LDK"
    assert domain.filters.get("pet_ok") is True
    # Unset filters must not appear in the TypedDict (total=False semantics)
    assert "max_walk_min" not in domain.filters
    assert "max_age" not in domain.filters


def test_to_search_response_maps_items() -> None:
    items = [
        SearchResultItem(
            property_id="P-001",
            final_rank=1,
            lexical_rank=1,
            semantic_rank=2,
            me5_score=0.5,
            score=0.99,
            attributions={"rent": 0.1, "_baseline": 0.0},
            popularity_score=0.4,
            title="渋谷のペット可1LDK",
            city="東京",
            ward="渋谷区",
            layout="1LDK",
            rent=180000,
            walk_min=8,
            age_years=6,
            area_m2=35.4,
            pet_ok=True,
        ),
    ]
    output = SearchOutput(
        request_id="r-1",
        items=items,
        model_path="gs://models/foo",
        ranked=[],
    )
    response = to_search_response(output)

    assert response.request_id == "r-1"
    assert response.model_path == "gs://models/foo"
    assert len(response.results) == 1
    assert response.results[0].property_id == "P-001"
    assert response.results[0].popularity_score == 0.4
    assert response.results[0].title == "渋谷のペット可1LDK"
    assert response.results[0].ward == "渋谷区"
    assert response.results[0].rent == 180000
    assert response.results[0].pet_ok is True
