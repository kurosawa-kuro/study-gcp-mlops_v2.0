"""Staged ``terraform apply`` for ``deploy-all`` (stage1 targeted + retries).

Separated from ``deploy_all.py`` so orchestration stays thin and lock / 409 logic
lives in one testable module alongside ``terraform_lock.py``.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from scripts._common import env
from scripts.infra.terraform_lock import (
    is_state_lock_error,
    parse_terraform_lock_id,
    should_auto_force_unlock,
)

# Keep in sync with ``infra/terraform`` — stage1 is kube-provider-free core.
TF_APPLY_STAGE1_TARGETS = (
    "module.iam",
    "module.data",
    "module.vector_search",
    "module.vertex",
    "module.gke",
    "module.messaging",
    "module.meilisearch",
    "module.monitoring",
    "module.slo",
    "module.composer",
)


def terraform_apply_stage1_with_retries(
    stage1_args: list[str],
    *,
    chdir_infra: Path,
) -> None:
    """Run stage1 apply; on state lock optionally force-unlock; on Vertex 409 sleep+retry."""
    max_attempts = int(env("TF_APPLY_STAGE1_MAX_ATTEMPTS", "5"))
    sleep_s = int(env("TF_APPLY_STAGE1_RETRY_SLEEP_SEC", "120"))
    for attempt in range(1, max_attempts + 1):
        proc = subprocess.run(
            stage1_args,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            if proc.stdout:
                print(proc.stdout)
            return

        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        print(combined[-12000:])

        if is_state_lock_error(combined):
            lock_id = parse_terraform_lock_id(combined)
            print(
                "\n==> Terraform state lock during deploy-all stage1.\n"
                f"    Lock ID: {lock_id or '(parse failed)'}\n"
                "    Wait for the other process, or set TERRAFORM_STATE_FORCE_UNLOCK=1 "
                "if the lock is stale.\n",
                flush=True,
            )
            if should_auto_force_unlock() and lock_id:
                unlock_cmd = [
                    "terraform",
                    f"-chdir={chdir_infra}",
                    "force-unlock",
                    "-force",
                    lock_id,
                ]
                print(f"==> TERRAFORM_STATE_FORCE_UNLOCK — {' '.join(unlock_cmd)}", flush=True)
                subprocess.run(unlock_cmd, check=True)
                print("==> retrying stage1 apply after force-unlock\n", flush=True)
                continue
            raise SystemExit(1)

        retryable = attempt < max_attempts and any(
            sig in combined
            for sig in (
                "Error 409",
                ": 409:",
                "being deleted",
                "Re-using the same name",
                "could not be created",
            )
        )
        if retryable:
            print(
                f"==> terraform apply stage1 attempt {attempt}/{max_attempts} failed "
                f"(Vertex eventual consistency?) — sleep {sleep_s}s then retry"
            )
            time.sleep(sleep_s)
            continue
        raise subprocess.CalledProcessError(
            proc.returncode, stage1_args, proc.stdout, proc.stderr
        )
