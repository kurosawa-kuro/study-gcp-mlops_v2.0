"""GCS bucket cleanup helpers for destroy-all.

Terraform-managed buckets (`*-models` / `*-artifacts` / `*-pipeline-root` /
`*-meili-data`) は `force_destroy = false` で作成されているので、object が
残ったままだと `terraform destroy` が
``Error trying to delete bucket ... containing objects without 'force_destroy'
set to true`` で fail する。本 module で `gcloud storage rm --recursive`
の薄ラッパーを提供して、destroy_all step 3/6 から呼ぶ。
"""

from __future__ import annotations

from scripts._common import env, run
from scripts.lib.gcp_resources import BUCKET_SUFFIXES


def wipe_bucket(project_id: str, bucket: str) -> None:
    """Recursively delete every object in one GCS bucket. Benign on absence.

    `gcloud storage rm --recursive gs://BUCKET/**` returns non-zero when the
    bucket doesn't exist or is already empty — both outcomes are fine here,
    so we suppress the error.
    """
    uri = f"gs://{bucket}"
    print(f"    wipe {uri}")
    run(
        [
            "gcloud",
            "storage",
            "rm",
            "--recursive",
            f"--project={project_id}",
            "--quiet",
            f"{uri}/**",
        ],
        check=False,
    )


def wipe_all_terraform_managed_buckets(project_id: str | None = None) -> None:
    """Iterate `BUCKET_SUFFIXES` and wipe each `<project>-<suffix>` bucket."""
    pid = project_id or env("PROJECT_ID")
    for suffix in BUCKET_SUFFIXES:
        wipe_bucket(pid, f"{pid}-{suffix}")
