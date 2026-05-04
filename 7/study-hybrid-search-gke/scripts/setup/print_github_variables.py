"""Emit `gh variable set` commands for the Variables consumed by deploy workflows.

`deploy-api.yml` / `deploy-*-image.yml` / `terraform.yml` read repository-level
GitHub Actions Variables via ``vars.<NAME>``. Since the sandbox can't modify
GitHub state, this script prints the commands so operators can ``| bash`` or
copy-paste them.

Missing values (Endpoint IDs before the first Python-SDK deploy, or the WIF
output before ``terraform apply``) come through as ``""`` so the emitted
command is still syntactically valid but clearly empty — the operator gets an
early signal to run the prerequisite step instead of silently shipping a
broken Cloud Run revision.
"""

from __future__ import annotations

import argparse
import shlex
from typing import Any

from scripts._common import env

# (variable name, description, env-var source) — the env-var fallbacks resolve
# via scripts._common.env, which falls through to env/config/setting.yaml.
VARIABLES: tuple[tuple[str, str, str], ...] = (
    ("WORKLOAD_IDENTITY_PROVIDER", "WIF provider resource name", "WORKLOAD_IDENTITY_PROVIDER"),
    ("DEPLOYER_SERVICE_ACCOUNT", "sa-github-deployer email", "DEPLOYER_SERVICE_ACCOUNT"),
    ("ONCALL_EMAIL", "alert notification email", "ONCALL_EMAIL"),
    ("VERTEX_LOCATION", "Vertex AI region", "VERTEX_LOCATION"),
    ("VERTEX_ENCODER_ENDPOINT_ID", "encoder Endpoint resource ID", "VERTEX_ENCODER_ENDPOINT_ID"),
    (
        "VERTEX_RERANKER_ENDPOINT_ID",
        "reranker Endpoint resource ID",
        "VERTEX_RERANKER_ENDPOINT_ID",
    ),
)


def build_variable_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, description, source_env in VARIABLES:
        value = env(source_env)
        rows.append(
            {
                "name": name,
                "description": description,
                "value": value,
                "resolved": bool(value),
            }
        )
    return rows


def build_gh_commands(repo: str) -> list[str]:
    cmds: list[str] = []
    for row in build_variable_rows():
        cmds.append(
            "gh variable set {name} --repo {repo} --body {value}".format(
                name=shlex.quote(row["name"]),
                repo=shlex.quote(repo),
                value=shlex.quote(str(row["value"])),
            )
        )
    return cmds


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit `gh variable set` commands for the repo's Actions variables"
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="owner/name form. Defaults to GITHUB_REPO from env/config/setting.yaml.",
    )
    args = parser.parse_args()

    repo = args.repo or env("GITHUB_REPO")
    if not repo:
        print("# GITHUB_REPO is empty; pass --repo owner/name or set it in setting.yaml")
        return 1

    rows = build_variable_rows()
    unresolved = [row["name"] for row in rows if not row["resolved"]]
    if unresolved:
        print(f"# Unresolved (empty) values — run prerequisites first: {', '.join(unresolved)}")
    for cmd in build_gh_commands(repo):
        print(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
