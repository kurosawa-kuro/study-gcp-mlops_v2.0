#!/usr/bin/env python3
"""Validate Dockerfile placement rules across phases."""

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


def _exists(relpath: str) -> bool:
    return (ROOT / relpath).is_file()


def _check_required() -> list[CheckResult]:
    required = [
        "2/study-ml-app-pipeline/infra/run/services/api/Dockerfile",
        "2/study-ml-app-pipeline/infra/run/jobs/trainer/Dockerfile",
        "3/study-hybrid-search-local/infra/run/services/search_api/Dockerfile",
        "4/study-hybrid-search-gcp/infra/run/services/search_api/Dockerfile",
        "4/study-hybrid-search-gcp/infra/run/jobs/embedding/Dockerfile",
        "4/study-hybrid-search-gcp/infra/run/jobs/training/Dockerfile",
        "5/study-hybrid-search-vertex/infra/run/jobs/embedding/Dockerfile",
        "5/study-hybrid-search-vertex/infra/run/jobs/training/Dockerfile",
        "5/study-hybrid-search-vertex/infra/run/services/encoder/Dockerfile",
        "5/study-hybrid-search-vertex/infra/run/services/reranker/Dockerfile",
        "5/study-hybrid-search-vertex/infra/run/services/search_api/Dockerfile",
        "1/study-ml-foundations/infra/run/jobs/trainer/Dockerfile",
    ]
    results: list[CheckResult] = []
    for rel in required:
        results.append(
            CheckResult(
                ok=_exists(rel),
                message=f"required: {rel}",
            )
        )
    return results


def _check_unexpected_suffix_dockerfiles() -> list[CheckResult]:
    allowed_suffix: set[str] = set()
    found = [p for p in ROOT.glob("**/Dockerfile.*") if p.is_file()]
    results: list[CheckResult] = []
    for path in sorted(found):
        rel = path.relative_to(ROOT).as_posix()
        ok = rel in allowed_suffix
        results.append(
            CheckResult(
                ok=ok,
                message=f"suffix-dockerfile: {rel}",
            )
        )
    if not found:
        results.append(CheckResult(ok=True, message="suffix-dockerfile: none"))
    return results


def _check_phase_layout_and_naming() -> list[CheckResult]:
    phase_roots = [
        ROOT / "2/study-ml-app-pipeline",
        ROOT / "3/study-hybrid-search-local",
        ROOT / "4/study-hybrid-search-gcp",
        ROOT / "5/study-hybrid-search-vertex",
    ]
    snake_case = re.compile(r"^[a-z0-9_]+$")
    results: list[CheckResult] = []

    for phase_root in phase_roots:
        rel_phase = phase_root.relative_to(ROOT).as_posix()
        dockerfiles = [p for p in phase_root.glob("**/Dockerfile") if p.is_file()]
        if not dockerfiles:
            results.append(
                CheckResult(ok=False, message=f"dockerfile-present: {rel_phase} has none")
            )
            continue

        for path in sorted(dockerfiles):
            rel = path.relative_to(ROOT).as_posix()
            parts = path.relative_to(phase_root).parts

            # Must be infra/run/jobs/<name>/Dockerfile or infra/run/services/<name>/Dockerfile.
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
                    ok=bool(snake_case.fullmatch(name)),
                    message=f"name: {rel}",
                )
            )

    return results


def main() -> int:
    checks = [
        *_check_required(),
        *_check_unexpected_suffix_dockerfiles(),
        *_check_phase_layout_and_naming(),
    ]
    failed = [c for c in checks if not c.ok]

    print("Docker layout check")
    print("===================")
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
