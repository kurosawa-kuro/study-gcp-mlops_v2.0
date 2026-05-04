"""Vertex train pipeline compile+submit for Composer `KubernetesPodOperator` (V5-8).

`retrain_orchestration` used to call `python -m pipeline.workflow.compile` with
argv containing shell-style ``$(GCP_PROJECT)`` strings. The pod receives those
literals (no shell expansion) and Vertex / KFP then fail in confusing ways. A
separate failure mode was ``FileNotFoundError: 'dist/pipelines'`` when the
process cwd or permissions did not match local `make` runs.

This entrypoint runs **inside composer-runner** at task execution time. Project
id uses :func:`scripts._common.resolve_project_id` (**GCP_PROJECT** from
Composer is canonical). Region / bucket use :func:`scripts._common.env` so
values come from **Composer ``env_variables``** (Terraform), not ``setting.yaml``.

Code/comments English per repo convention.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts._common import env, resolve_project_id


def main() -> int:
    from pipeline.workflow import compile as compile_mod

    project = resolve_project_id()
    if not project:
        print(
            "[error] submit_train_pipeline: GCP_PROJECT missing — Composer must inject it. "
            "Extend infra/terraform/modules/composer env_variables; do not rely on editing "
            "env/config/setting.yaml for live.",
            file=sys.stderr,
        )
        return 1

    location = (env("VERTEX_LOCATION") or env("REGION") or "").strip() or "asia-northeast1"

    bucket = env("PIPELINE_ROOT_BUCKET").strip()
    if not bucket:
        print(
            "[error] submit_train_pipeline: PIPELINE_ROOT_BUCKET missing — "
            "set in Terraform Composer env_variables and propagate via _pod.py",
            file=sys.stderr,
        )
        return 1

    output_dir = Path("/tmp/pipelines")
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_root = f"gs://{bucket}/runs"
    service_account = f"sa-pipeline@{project}.iam.gserviceaccount.com"

    sys.argv = [
        "compile",
        "--target",
        "train",
        "--output-dir",
        str(output_dir),
        "--submit",
        "--project-id",
        project,
        "--location",
        location,
        "--pipeline-root",
        pipeline_root,
        "--service-account",
        service_account,
    ]
    return compile_mod.main()


if __name__ == "__main__":
    raise SystemExit(main())
