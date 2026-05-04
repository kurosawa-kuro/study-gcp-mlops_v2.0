"""Phase 0 bootstrap (idempotent): enable required APIs + create the tfstate
bucket. Needs project Owner / Service Usage Admin / Storage Admin on the
caller. Re-running is safe; both ops are no-ops when already in place.
"""

from __future__ import annotations

import subprocess
import sys

from scripts._common import env, gcloud, run

REQUIRED_APIS = [
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "bigquery.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "dataform.googleapis.com",
    "pubsub.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "eventarc.googleapis.com",
    "bigquerydatatransfer.googleapis.com",
    "cloudbuild.googleapis.com",
]


def main() -> int:
    project_id = env("PROJECT_ID")
    region = env("REGION")
    bucket = f"{project_id}-tfstate"

    print(f"==> Enabling required APIs on {project_id}...", flush=True)
    run(["gcloud", "services", "enable", f"--project={project_id}", *REQUIRED_APIS])

    print(f"==> Creating gs://{bucket} if absent...", flush=True)
    exists = subprocess.run(
        ["gcloud", "storage", "buckets", "describe", f"gs://{bucket}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if exists.returncode == 0:
        print("    already exists — skipping create")
    else:
        gcloud(
            "storage",
            "buckets",
            "create",
            f"gs://{bucket}",
            f"--project={project_id}",
            f"--location={region}",
            "--uniform-bucket-level-access",
            "--public-access-prevention",
        )
        gcloud("storage", "buckets", "update", f"gs://{bucket}", "--versioning")

    print(
        "==> Done. Next: make tf-init && "
        "make tf-plan GITHUB_REPO=<owner>/<name> ONCALL_EMAIL=<mail>",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
