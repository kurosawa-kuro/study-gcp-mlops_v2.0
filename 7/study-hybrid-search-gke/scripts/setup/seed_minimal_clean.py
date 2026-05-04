"""Remove everything `scripts.setup.seed_minimal` wrote. Symmetric with
`make seed-test`.

Drops:
- `feature_mart.properties_cleaned` — out-of-Terraform-state TABLE created
  by `seed_minimal.py::CREATE OR REPLACE TABLE`. If left behind during a
  `terraform destroy`, the `feature_mart` dataset drop fails with
  `resourceInUse` (dataset has a table Terraform does not know about).
- Today's rows from `feature_mart.property_features_daily`.
- All rows from `feature_mart.property_embeddings`.

Idempotent: missing tables / rows are tolerated (`bq rm -f` / `DELETE`
with no-op predicate). Useful standalone for `make seed-test-clean` and
reused as step 1 of `make destroy-all`.
"""

from __future__ import annotations

import subprocess

from scripts._common import env


def main() -> int:
    project_id = env("PROJECT_ID")

    print("==> drop feature_mart.properties_cleaned (out-of-TF, benign if absent)")
    subprocess.run(
        [
            "bq",
            "rm",
            "-f",
            "-t",
            f"--project_id={project_id}",
            "feature_mart.properties_cleaned",
        ],
        check=False,
    )

    print("==> delete today's rows from feature_mart.property_features_daily")
    subprocess.run(
        [
            "bq",
            "query",
            "--use_legacy_sql=false",
            f"--project_id={project_id}",
            f"DELETE FROM `{project_id}.feature_mart.property_features_daily` "
            f"WHERE event_date = CURRENT_DATE('Asia/Tokyo')",
        ],
        check=False,
    )

    print("==> delete all rows from feature_mart.property_embeddings")
    subprocess.run(
        [
            "bq",
            "query",
            "--use_legacy_sql=false",
            f"--project_id={project_id}",
            f"DELETE FROM `{project_id}.feature_mart.property_embeddings` WHERE TRUE",
        ],
        check=False,
    )

    print()
    print("==> seed-test-clean complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
