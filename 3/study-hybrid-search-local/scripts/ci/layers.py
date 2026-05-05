"""Phase 3 — AST-based Port-Adapter boundary checker.

Phase 7 の ``scripts/ci/layers.py`` を Phase 3 用に簡素化。

ルール:
- ``app/services/protocols/`` は adapter / SDK / 外部 import 禁止
- ``app/services/{search,ranking,feedback}_service.py`` は adapter import 禁止
- ``app/domain/`` / ``app/schemas/`` は外部 SDK / lightgbm import 禁止
- ``app/api/middleware/`` は google.cloud import 禁止
- 全 phase で google.cloud / kserve / kfp import 禁止 (誤投下防止)

実行: ``uv run python -m scripts.ci.layers`` / ``make check-layers``
非ゼロ終了 = 違反あり。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# (file path glob, forbidden module prefixes)
FORBIDDEN_RULES: list[tuple[str, list[str]]] = [
    (
        "app/services/protocols/**/*.py",
        [
            "app.services.adapters",
            "google.cloud",
            "kserve",
            "kfp",
            "lightgbm",
            "sentence_transformers",
            "psycopg",
            "meilisearch",
            "redis",
        ],
    ),
    (
        "app/services/search_service.py",
        ["app.services.adapters", "google.cloud", "lightgbm", "psycopg", "redis"],
    ),
    (
        "app/services/ranking.py",
        ["app.services.adapters", "google.cloud", "lightgbm", "psycopg", "redis"],
    ),
    (
        "app/services/feedback_service.py",
        ["app.services.adapters", "google.cloud", "psycopg", "redis"],
    ),
    ("app/domain/**/*.py", ["google.cloud", "lightgbm", "psycopg", "meilisearch"]),
    ("app/schemas/**/*.py", ["google.cloud", "lightgbm", "psycopg", "meilisearch"]),
    ("app/api/middleware/**/*.py", ["google.cloud"]),
    ("app/**/*.py", ["google.cloud", "kserve", "kfp"]),
    ("ml/**/*.py", ["google.cloud", "kserve", "kfp"]),
    ("pipeline/**/*.py", ["google.cloud", "kserve", "kfp"]),
]


def _imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _matches(prefix: str, module: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def main() -> int:
    violations: list[str] = []
    for glob, forbidden in FORBIDDEN_RULES:
        for path in ROOT.glob(glob):
            if not path.is_file() or path.suffix != ".py":
                continue
            mods = _imports(path)
            for prefix in forbidden:
                hits = [m for m in mods if _matches(prefix, m)]
                if hits:
                    rel = path.relative_to(ROOT)
                    violations.append(
                        f"❌ {rel}: forbidden import of {', '.join(sorted(hits))} (rule: {prefix})"
                    )

    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        print(f"\n{len(violations)} layer-boundary violation(s) found", file=sys.stderr)
        return 1

    print(f"✓ Port-Adapter boundary OK ({len(FORBIDDEN_RULES)} rules checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
