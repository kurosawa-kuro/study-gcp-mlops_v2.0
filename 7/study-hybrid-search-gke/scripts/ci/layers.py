"""AST-based layer boundary checker (MLOps skeleton edition).

Walks every Port / pure-logic module and reports any forbidden import
(concrete adapter, GCP SDK, LightGBM where inapplicable). Each file
is inspected at *every* `Import` / `ImportFrom` node — top-level AND
inside functions — so lazy imports cannot smuggle a banned dependency
back in.

Two consumers share the canonical ruleset declared here:

- ``tests/unit/arch/test_import_boundaries.py`` imports ``RULES``,
  ``DIRECTORY_RULES``, ``UNIVERSAL_BANS``, and ``find_violations()`` so
  pytest cases stay aligned with this script.
- ``make check-layers`` runs ``python -m scripts.ci.layers`` for ad-hoc
  inspection outside pytest. Exit code 0 = clean, 1 = violations found,
  with ``<rel_path>:<line>`` references for every offending import.

Phase F-2 added auto-discovery: instead of (or in addition to) listing
every file in ``RULES``, callers can declare a ``DIRECTORY_RULES``
entry that applies to every ``.py`` under that directory subtree. Files
not covered by either ``RULES`` or ``DIRECTORY_RULES`` are unrestricted
(only ``UNIVERSAL_BANS`` apply). To add a per-file override that
diverges from the directory default, add it to ``RULES`` — file-level
rules win.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every Port / pure-logic file is disallowed from importing these at all.
UNIVERSAL_BANS: frozenset[str] = frozenset()

# Concrete GCP / runtime integrations that must not leak into pure-logic
# modules (protocols, pure functions, schemas).
ADAPTER_BANS: frozenset[str] = frozenset({"google.cloud"})


# ---------------------------------------------------------------------- file rules

# Per-file overrides. Use sparingly — most files should be covered by
# ``DIRECTORY_RULES``. Entries here override directory-level rules.
RULES: dict[str, frozenset[str]] = {
    # --- ml/common (varying restrictions per file) ---
    "ml/common/config/base.py": ADAPTER_BANS | frozenset({"lightgbm"}),
    "ml/common/logging/structured_logging.py": ADAPTER_BANS
    | frozenset({"lightgbm", "pandas", "numpy"}),
    "ml/common/utils/run_id.py": ADAPTER_BANS | frozenset({"lightgbm", "pandas", "numpy"}),
    # --- ml/data/feature_engineering (pure logic) ---
    "ml/data/feature_engineering/schema.py": ADAPTER_BANS
    | frozenset({"lightgbm", "pandas", "numpy"}),
    "ml/data/feature_engineering/ranker_features.py": ADAPTER_BANS | frozenset({"lightgbm"}),
    # --- ml/evaluation/metrics ---
    "ml/evaluation/metrics/ranking.py": ADAPTER_BANS | frozenset({"lightgbm", "pandas"}),
    "ml/evaluation/metrics/label_gain.py": ADAPTER_BANS
    | frozenset({"lightgbm", "pandas", "numpy"}),
    # --- app/services overrides (services have heterogeneous extra bans) ---
    "app/services/ranking.py": ADAPTER_BANS | frozenset({"sentence_transformers"}),
    "app/services/search_service.py": ADAPTER_BANS | frozenset({"sentence_transformers"}),
    # --- app/schemas (Pydantic + extra bans) ---
    "app/schemas/search.py": ADAPTER_BANS | frozenset({"lightgbm", "numpy"}),
}


# ----------------------------------------------------------------- directory rules

# Directory-level rules: every ``.py`` under the prefix gets these bans
# (unless overridden by ``RULES``). Longest matching prefix wins.
#
# Order matters for readability only — ``find_rules_for_file`` walks all
# entries and picks the longest match.
DIRECTORY_RULES: dict[str, frozenset[str]] = {
    # app/ Ports + Domain + pure-logic services
    "app/domain/": ADAPTER_BANS | frozenset({"lightgbm"}),
    "app/services/protocols/": ADAPTER_BANS | frozenset({"lightgbm"}),
    "app/services/noop_adapters/": ADAPTER_BANS,
    # app/api/ — routers + mappers + middleware + DI resolvers (no SDK)
    "app/api/routers/": ADAPTER_BANS,
    "app/api/mappers/": ADAPTER_BANS,
    "app/api/middleware/": ADAPTER_BANS,
    # ml/<feature>/ports/ — every Port file is SDK-free
    "ml/training/ports/": ADAPTER_BANS | frozenset({"lightgbm"}),
    "ml/training/experiments/ports/": ADAPTER_BANS | frozenset({"lightgbm"}),
    "ml/registry/ports/": ADAPTER_BANS,
    "ml/serving/ports/": ADAPTER_BANS,
    "ml/streaming/ports/": ADAPTER_BANS,
    # pipeline/<job>/ports/ — canonical lives under ``pipeline/training_job/ports``.
    # data/eval/batch_serving jobs pull Ports via direct
    # ``from pipeline.training_job.ports import ...``.
    "pipeline/training_job/ports/": ADAPTER_BANS | frozenset({"kfp"}),
    # pipeline/dags/ — Composer (Airflow Gen 3) DAG files. airflow / google.cloud /
    # scripts.* import 可 (Composer worker が動かす)、ただし `app.*` import 禁止
    # — search-api コードを Composer worker が引っ張ると import が重く scheduler
    # reparse コストが膨らむため。Phase 7 W2-4 で追加。
    "pipeline/dags/": frozenset({"app"}),
    # app/services/* (top-level files only — adapters/protocols/fakes are
    # carved out below). Protocol Ports never import google.cloud, plain
    # services delegate to Ports. Composition root is the explicit
    # exception (see EXCLUSIONS).
    "app/services/": ADAPTER_BANS,
}

# Files / directories that are excused from auto-discovery despite living
# under one of the directory prefixes above. Matched by exact relative
# path or by directory prefix (with trailing slash).
EXCLUSIONS: frozenset[str] = frozenset(
    {
        # Composition root must instantiate adapters → must import google.cloud
        "app/composition_root.py",
        # HTTP entrypoint — re-exports nothing forbidden but allowed by design
        "app/main.py",
        # Adapters MUST be allowed to import any concrete SDK
        "app/services/adapters/",
        # Test doubles + framework
        "tests/",
    }
)


# ----------------------------------------------------------------------- machinery


@dataclass(frozen=True)
class Violation:
    """One forbidden import in one file."""

    rel_path: str
    line: int
    imported: str
    banned_prefix: str

    def __str__(self) -> str:
        return (
            f"{self.rel_path}:{self.line}  import {self.imported!r} "
            f"hits banned prefix {self.banned_prefix!r}"
        )


def _imports_with_lines(path: Path) -> list[tuple[int, str]]:
    """Every imported module name + the source line where it appears."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def _matches(imported: str, banned: str) -> bool:
    """Prefix match: imported equals ``banned`` itself or is one of its submodules."""
    return imported == banned or imported.startswith(banned + ".")


def _is_excluded(rel_path: str) -> bool:
    if rel_path in EXCLUSIONS:
        return True
    return any(rel_path.startswith(prefix) for prefix in EXCLUSIONS if prefix.endswith("/"))


def find_rules_for_file(rel_path: str) -> frozenset[str] | None:
    """Resolve the ban set for a path, or ``None`` if the file is unrestricted.

    Resolution order:
    1. Exclusion list (returns ``None``)
    2. File-level ``RULES`` (exact match wins)
    3. Longest matching ``DIRECTORY_RULES`` prefix
    4. ``None`` if no rule applies (only ``UNIVERSAL_BANS`` enforced)
    """
    if _is_excluded(rel_path):
        return None
    if rel_path in RULES:
        return RULES[rel_path]
    matched_prefix = ""
    for prefix in DIRECTORY_RULES:
        if rel_path.startswith(prefix) and len(prefix) > len(matched_prefix):
            matched_prefix = prefix
    if matched_prefix:
        return DIRECTORY_RULES[matched_prefix]
    return None


def find_violations(rel_path: str) -> list[Violation]:
    """Return every ``(line, imported, banned_prefix)`` violation in the given file."""
    path = REPO_ROOT / rel_path
    if not path.exists():
        return [Violation(rel_path, 0, "<missing source file>", "")]

    rules = find_rules_for_file(rel_path)
    bans = UNIVERSAL_BANS if rules is None else UNIVERSAL_BANS | rules

    found: list[Violation] = []
    for line, imp in _imports_with_lines(path):
        for banned in bans:
            if _matches(imp, banned):
                found.append(Violation(rel_path, line, imp, banned))
    return sorted(found, key=lambda v: (v.rel_path, v.line, v.imported))


def discover_files() -> list[str]:
    """Walk app/ + ml/ + pipeline/ to find every .py file under a rule.

    Returns relative paths (POSIX-style) sorted ascending. ``__init__.py``
    files are skipped because re-export modules tend to import every
    public symbol — including legitimate adapter classes — and that
    would create false positives. Adapter directories are excluded too.
    """
    seen: set[str] = set()
    for root in ("app", "ml", "pipeline"):
        root_path = REPO_ROOT / root
        if not root_path.exists():
            continue
        for path in root_path.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path.name == "__init__.py":
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if find_rules_for_file(rel) is None:
                # Either explicitly excluded or no rule applies.
                continue
            seen.add(rel)
    # Also include any explicit RULES entry that the walk missed (e.g.
    # files outside app/ml/pipeline) so removed-rule drift is caught.
    for rel in RULES:
        if find_rules_for_file(rel) is not None:
            seen.add(rel)
    return sorted(seen)


def main() -> int:
    rel_paths = discover_files()
    total = 0
    for rel_path in rel_paths:
        for v in find_violations(rel_path):
            print(v)
            total += 1
    if total == 0:
        print(f"check-layers: OK ({len(rel_paths)} files clean)")
        return 0
    print(
        f"check-layers: FAIL ({total} violations across {len(rel_paths)} files)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
