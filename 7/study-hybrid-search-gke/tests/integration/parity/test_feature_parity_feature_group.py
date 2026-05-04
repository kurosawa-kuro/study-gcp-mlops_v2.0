"""Feature-parity check: Vertex Feature Group property-side features ↔ ranker schema.

The Vertex Feature Group excludes query-time signals, so it must match the
property-side subset of ``FEATURE_COLS_RANKER`` exactly:

* rent
* walk_min
* age_years
* area_m2
* ctr
* fav_rate
* inquiry_rate
"""

from __future__ import annotations

import re

from tests.integration.parity.parity_invariant import PROPERTY_SIDE_COLS, REPO_ROOT

VERTEX_MODULE_PATH = REPO_ROOT / "infra" / "terraform" / "modules" / "vertex" / "main.tf"

_FEATURE_GROUP_BLOCK_RE = re.compile(
    r"feature_group_property_features\s*=\s*\[(?P<body>.*?)\n\s*\]",
    re.DOTALL,
)
_FEATURE_NAME_RE = re.compile(r'name\s*=\s*"(?P<name>[^"]+)"')
_VALUE_TYPE_RE = re.compile(r'value_type\s*=\s*"(?P<value_type>[^"]+)"')


def _extract_feature_group_block() -> str:
    text = VERTEX_MODULE_PATH.read_text()
    match = _FEATURE_GROUP_BLOCK_RE.search(text)
    assert match is not None, (
        "feature_group_property_features block not found in "
        f"{VERTEX_MODULE_PATH}. Keep the Vertex Feature Group scaffold in sync."
    )
    return match["body"]


def _extract_feature_group_names() -> list[str]:
    return [m["name"] for m in _FEATURE_NAME_RE.finditer(_extract_feature_group_block())]


def _extract_feature_group_value_types() -> list[str]:
    return [m["value_type"] for m in _VALUE_TYPE_RE.finditer(_extract_feature_group_block())]


def test_vertex_feature_group_order_matches_property_side_cols() -> None:
    assert _extract_feature_group_names() == PROPERTY_SIDE_COLS, (
        "Vertex Feature Group property-side feature order diverged from "
        f"FEATURE_COLS_RANKER subset. Vertex: {_extract_feature_group_names()} "
        f"Expected: {PROPERTY_SIDE_COLS}"
    )


def test_vertex_feature_group_uses_double_features() -> None:
    value_types = _extract_feature_group_value_types()
    assert value_types == ["DOUBLE"] * len(PROPERTY_SIDE_COLS), (
        f"Vertex Feature Group should currently declare DOUBLE features only; got {value_types}"
    )
