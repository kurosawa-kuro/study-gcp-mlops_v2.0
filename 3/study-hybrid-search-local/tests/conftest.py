"""Phase 3 — pytest 共通 fixtures.

GCP / KServe / Vertex 由来の fixture は除外。
"""

from __future__ import annotations

import pytest

from app.domain.candidate import Candidate
from app.domain.search import SearchFilters


@pytest.fixture
def sample_candidate() -> Candidate:
    return Candidate(
        property_id="prop-0001",
        lexical_rank=1,
        semantic_rank=2,
        me5_score=0.85,
        property_features={
            "rent": 120_000,
            "walk_min": 5,
            "age_years": 10,
            "area_m2": 35.0,
            "ctr": 0.05,
            "fav_rate": 0.01,
            "inquiry_rate": 0.005,
        },
    )


@pytest.fixture
def empty_filters() -> SearchFilters:
    return SearchFilters()
