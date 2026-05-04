"""Preflight-check the tfstate bucket (created by `make tf-bootstrap`) before
running `terraform init`. Aborts with a clear error if the bucket is missing
instead of letting terraform fail with the noisier backend error.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts._common import env, fail, run

INFRA = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "environments" / "dev"


def main() -> int:
    project_id = env("PROJECT_ID")
    bucket = f"{project_id}-tfstate"

    exists = subprocess.run(
        ["gcloud", "storage", "buckets", "describe", f"gs://{bucket}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if exists.returncode != 0:
        return fail(
            f"ERROR: gs://{bucket} does not exist.\n"
            "       Run 'make tf-bootstrap' first (Phase 0, one-time).\n"
            "       For offline syntax-only validation use 'make tf-validate'."
        )

    run(["terraform", f"-chdir={INFRA}", "init"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
