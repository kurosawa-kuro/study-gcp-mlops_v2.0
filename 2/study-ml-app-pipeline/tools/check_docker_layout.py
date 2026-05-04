#!/usr/bin/env python3
"""Validate Dockerfile placement rules for this phase."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str


ROOT = Path(__file__).resolve().parents[1]
SNAKE_CASE = re.compile(r"^[a-z0-9_]+$")
REQUIRED = [
    "infra/run/jobs/trainer/Dockerfile",
]


def _exists(relpath: str) -> bool:
    return (ROOT / relpath).is_file()


def _check_required() -> list[CheckResult]:
    return [CheckResult(ok=_exists(rel), message=f"required: {rel}") for rel in REQUIRED]


def _check_no_suffix_dockerfiles() -> list[CheckResult]:
    found = [p for p in ROOT.glob("**/Dockerfile.*") if p.is_file()]

    if not found:
        return [CheckResult(ok=True, message="suffix-dockerfile: none")]

    return [
        CheckResult(ok=False, message=f"suffix-dockerfile: {p.relative_to(ROOT).as_posix()}")
        for p in sorted(found)
    ]


def _check_layout_and_naming() -> list[CheckResult]:
    dockerfiles = [p for p in ROOT.glob("**/Dockerfile") if p.is_file()]
    if not dockerfiles:
        return [CheckResult(ok=False, message="dockerfile-present: none")]

    results: list[CheckResult] = []
    for path in sorted(dockerfiles):
        rel = path.relative_to(ROOT).as_posix()
        parts = path.relative_to(ROOT).parts

        ok_shape = (
            len(parts) == 5
            and parts[0] == "infra"
            and parts[1] == "run"
            and parts[2] in {"jobs", "services"}
            and parts[4] == "Dockerfile"
        )
        if not ok_shape:
            results.append(CheckResult(ok=False, message=f"layout: {rel}"))
            continue

        name = parts[3]
        results.append(
            CheckResult(
                ok=bool(SNAKE_CASE.fullmatch(name)),
                message=f"name: {rel}",
            )
        )

    return results


def main() -> int:
    checks = [
        *_check_required(),
        *_check_no_suffix_dockerfiles(),
        *_check_layout_and_naming(),
    ]
    failed = [c for c in checks if not c.ok]

    print("Docker layout check (phase-local)")
    print("=================================")
    for c in checks:
        status = "OK" if c.ok else "NG"
        print(f"[{status}] {c.message}")

    if failed:
        print(f"\nResult: FAILED ({len(failed)} issue(s))")
        return 1

    print("\nResult: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
