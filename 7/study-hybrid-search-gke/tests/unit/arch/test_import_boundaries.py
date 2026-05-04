"""Architectural boundary checks — enforced at CI time via AST.

The canonical ruleset and the AST scanner live in
``scripts/ci/layers.py``; this test module just wraps every Port /
service / Pure-logic file in its own pytest case so a failure points
cleanly at the offending file.

Phase F-2 added directory-level auto-discovery: every ``.py`` file under
``app/services/protocols/``, ``app/services/noop_adapters/``, ``app/domain/``,
``app/api/routers``/``mappers``/``middleware``, ``app/services/``
(top-level), ``ml/<feature>/ports/`` and ``pipeline/<job>/ports/``
becomes a test case automatically. To add a per-file override that
diverges from the directory default, edit
``scripts/ci/layers.py::RULES``. To add a wholly new directory-level
rule, edit ``DIRECTORY_RULES`` there.

The check is intentionally shallow: each file is inspected at every
``Import`` / ``ImportFrom`` node — top-level AND inside functions — so
lazy imports cannot smuggle a forbidden dependency back in. Transitive
imports via adapters are allowed (that is the whole point of
Port/Adapter).
"""

from __future__ import annotations

import pytest

from scripts.ci.layers import REPO_ROOT, discover_files, find_violations


@pytest.mark.parametrize("rel_path", discover_files())
def test_no_forbidden_imports(rel_path: str) -> None:
    assert (REPO_ROOT / rel_path).exists(), f"source file missing: {rel_path}"

    violations = find_violations(rel_path)
    assert not violations, (
        f"{rel_path} imports forbidden modules: "
        f"{[(v.imported, v.banned_prefix) for v in violations]}. "
        "Move external-SDK / concrete-adapter usage into the adapters/composition root."
    )
