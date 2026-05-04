"""Feature-parity check: infra/sql/monitoring/validate_feature_skew.sql UNPIVOT ↔ property-side ranker cols.

``validate_feature_skew.sql`` lists the property-side feature subset twice
(training + serving UNPIVOT). Both lists must match the 7 property-side
columns drawn from ``FEATURE_COLS_RANKER`` — i.e. every column in
``FEATURE_COLS_RANKER`` *except* ``me5_score`` / ``lexical_rank`` /
``semantic_rank`` (which are
query-time signals with no training-side representation; they are monitored
via separate sentinels in the same SQL).
"""

from __future__ import annotations

import re

import pytest

from tests.integration.parity.parity_invariant import PROPERTY_SIDE_COLS, REPO_ROOT

SQL_PATH = REPO_ROOT / "infra" / "sql" / "monitoring" / "validate_feature_skew.sql"

_UNPIVOT_RE = re.compile(
    r"UNPIVOT\s*\(\s*value\s+FOR\s+feature_name\s+IN\s*\((?P<cols>[^)]+)\)\s*\)",
    re.IGNORECASE | re.DOTALL,
)


def _extract_unpivot_feature_lists() -> list[list[str]]:
    text = SQL_PATH.read_text()
    lists: list[list[str]] = []
    for match in _UNPIVOT_RE.finditer(text):
        raw = match.group("cols")
        cols = [c.strip().strip("`") for c in raw.split(",") if c.strip()]
        lists.append(cols)
    return lists


def test_ranker_sql_file_exists() -> None:
    assert SQL_PATH.exists(), f"missing: {SQL_PATH}"


def test_ranker_sql_has_both_unpivots() -> None:
    lists = _extract_unpivot_feature_lists()
    assert len(lists) == 2, (
        f"expected 2 UNPIVOT blocks (training + serving) in {SQL_PATH}, found {len(lists)}"
    )


@pytest.mark.parametrize("block_index", [0, 1])
def test_ranker_unpivot_matches_property_side_cols(block_index: int) -> None:
    lists = _extract_unpivot_feature_lists()
    assert block_index < len(lists), "UNPIVOT block missing"
    assert lists[block_index] == PROPERTY_SIDE_COLS, (
        f"UNPIVOT #{block_index} diverged from property-side FEATURE_COLS_RANKER. "
        f"SQL: {lists[block_index]}. Expected: {PROPERTY_SIDE_COLS}. "
        "Update the UNPIVOT list to match feature_schema.FEATURE_COLS_RANKER "
        "(minus me5_score / lexical_rank / semantic_rank which are query-time signals)."
    )


def test_ranker_sql_reads_ranking_log_not_predictions_log() -> None:
    """Serving window source must be ranking_log, not the legacy predictions_log."""
    text = SQL_PATH.read_text()
    assert "mlops.ranking_log" in text
    assert "mlops.predictions_log" not in text
