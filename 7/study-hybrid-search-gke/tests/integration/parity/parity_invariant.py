"""Shared invariants/helpers for parity tests.

The Python schema (`ml.data.feature_engineering.FEATURE_COLS_RANKER`) is the
canonical source of truth. Parity tests import helpers from here rather than
re-deriving the same subsets and parsers in each file.

Conventions for new parity tests:

- ``from tests.integration.parity.parity_invariant import REPO_ROOT`` —
  do NOT redefine ``Path(__file__).resolve().parents[3]`` per file.
- Use ``read_text(path)`` for plain file reads (encoding centralised).
- Use ``extract_terraform_block(text, resource_type=..., name=...)``
  when you need a brace-balanced ``resource "..." "..." {...}`` body
  out of a ``main.tf``.
- Use ``flat_yaml(text)`` for the simple ``key: value`` dialect of
  ``setting.yaml`` / ``workflow_settings.yaml``.

When adding a new parity invariant, document the **registration criteria**
in ``tests/integration/parity/README.md`` (which files lock-step, why,
and what regression the test prevents).
"""

from __future__ import annotations

import re
from pathlib import Path

from ml.data.feature_engineering import FEATURE_COLS_RANKER

REPO_ROOT = Path(__file__).resolve().parents[3]
QUERY_TIME_COLS = {"me5_score", "lexical_rank", "semantic_rank"}
PROPERTY_SIDE_COLS: list[str] = [col for col in FEATURE_COLS_RANKER if col not in QUERY_TIME_COLS]


def read_text(path: Path) -> str:
    """Read a file as UTF-8. Centralised so all parity tests agree on encoding."""
    return path.read_text(encoding="utf-8")


def flat_yaml(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def extract_terraform_block(text: str, *, resource_type: str, name: str) -> str | None:
    """Return the body of ``resource "<resource_type>" "<name>" {...}`` in ``text``.

    Brace-balanced extraction so nested ``{}`` blocks (record schemas,
    dynamic blocks, ...) round-trip correctly. Returns the inner body
    (without the outer ``{`` / ``}``) or ``None`` if the resource is
    absent. Use for parity assertions over Terraform module sources.
    """
    pattern = re.compile(
        rf'resource\s+"{re.escape(resource_type)}"\s+"{re.escape(name)}"\s*{{',
    )
    match = pattern.search(text)
    if match is None:
        return None
    start = match.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return text[start : i - 1]
