"""Verify prerequisite tools are installed (called by `make doctor`).

Required: uv, terraform, make, python3 (jq + gcloud are convenience-only).
Also warns if VIRTUAL_ENV points outside the project's .venv (uv ignores it
but the mismatch is a common confusion source).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# doctor.py is intentionally stdlib-only — `_common` is also stdlib but we
# avoid the import here so `make doctor` works even before `make sync`.

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

TOOLS = ["uv", "terraform", "gcloud", "make", "python3", "jq"]
OPTIONAL = {"jq", "gcloud"}


def _version(tool: str) -> str:
    proc = subprocess.run([tool, "--version"], check=False, capture_output=True, text=True)
    out = proc.stdout or proc.stderr
    return out.splitlines()[0] if out else ""


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    missing = 0

    for tool in TOOLS:
        if shutil.which(tool):
            print(f"  {GREEN}OK{RESET}   {tool:<10}  {_version(tool)}")
        else:
            print(f"  {RED}MISS{RESET} {tool:<10}  (see README.md §セットアップ for install)")
            if tool not in OPTIONAL:
                missing = 1

    venv = os.environ.get("VIRTUAL_ENV", "")
    project_venv = str(root / ".venv")
    if venv and venv != project_venv:
        print(
            f"  {YELLOW}WARN{RESET} VIRTUAL_ENV={venv} は project 外。"
            f"uv は {project_venv} を使うため無視される。"
            "'deactivate' してから make を実行することを推奨。"
        )

    if missing:
        print()
        print("Required tools missing — install them before 'make sync'.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
