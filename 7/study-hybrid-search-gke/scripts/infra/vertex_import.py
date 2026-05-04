"""Vertex Vector Search の Index / Index Endpoint を Terraform state に import する。

Phase 7 永続化アーキテクチャ (`docs/tasks/TASKS_ROADMAP.md §4.9`、2026-05-03):
`destroy-all` は `module.vector_search` の Index / Endpoint を **state rm + GCP
残置** する。次回 `deploy-all` の tf-apply 前に本 module を呼んで:

- GCP 上に該当 resource があれば **state に import** (= terraform plan で
  「既存」として認識される、`deployed_index` のみ create される設計)
- GCP 上にも無ければ skip (= terraform plan で全 resource を新規 create する初回 deploy)
- state に既に entry があれば skip (= 既に同期済の冪等な再実行)

これで deploy-all は 27 min → 10-15 min に短縮される (Index build 5-15 min +
Endpoint create + DNS propagation を 2 回目以降は省略できる)。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

INDEX_ADDR = "module.vector_search.google_vertex_ai_index.property_embeddings[0]"
ENDPOINT_ADDR = "module.vector_search.google_vertex_ai_index_endpoint.property_embeddings[0]"


def _state_has(infra_dir: Path, addr: str) -> bool:
    proc = subprocess.run(
        ["terraform", f"-chdir={infra_dir}", "state", "list", addr],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and addr in (proc.stdout or "")


def _gcloud_first(args: list[str]) -> dict | None:
    """Run a `gcloud ... list --format=json` and return the first item, or None."""
    proc = subprocess.run(args, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    payload = json.loads(proc.stdout) if (proc.stdout or "").strip() else []
    return payload[0] if isinstance(payload, list) and payload else None


def _terraform_import(
    infra_dir: Path, addr: str, gcp_id: str, *, terraform_var_args: list[str]
) -> bool:
    print(f"==> terraform import {addr} ← {gcp_id}")
    proc = subprocess.run(
        [
            "terraform",
            f"-chdir={infra_dir}",
            "import",
            *terraform_var_args,
            addr,
            gcp_id,
        ],
        check=False,
    )
    return proc.returncode == 0


def import_persistent_vvs_resources(
    infra_dir: Path,
    project_id: str,
    region: str,
    *,
    terraform_var_args: list[str] | None = None,
) -> int:
    """Import persistent VVS Index / Endpoint into state if missing.

    Returns the number of resources imported.
    """
    var_args = list(terraform_var_args or [])
    imported = 0

    # ---- Index Endpoint ----
    if _state_has(infra_dir, ENDPOINT_ADDR):
        print(f"==> {ENDPOINT_ADDR} は state に existing — import skip")
    else:
        endpoint = _gcloud_first(
            [
                "gcloud",
                "ai",
                "index-endpoints",
                "list",
                f"--region={region}",
                f"--project={project_id}",
                "--format=json",
            ]
        )
        if endpoint and endpoint.get("name"):
            # gcloud は numeric project の resource name を返す。Terraform import は
            # この form をそのまま受ける。
            if _terraform_import(
                infra_dir, ENDPOINT_ADDR, endpoint["name"], terraform_var_args=var_args
            ):
                imported += 1
        else:
            print(f"==> {ENDPOINT_ADDR}: GCP にも state にも存在しない — 初回 deploy 扱いで skip")

    # ---- Index ----
    if _state_has(infra_dir, INDEX_ADDR):
        print(f"==> {INDEX_ADDR} は state に existing — import skip")
    else:
        index = _gcloud_first(
            [
                "gcloud",
                "ai",
                "indexes",
                "list",
                f"--region={region}",
                f"--project={project_id}",
                "--format=json",
            ]
        )
        if index and index.get("name"):
            if _terraform_import(infra_dir, INDEX_ADDR, index["name"], terraform_var_args=var_args):
                imported += 1
        else:
            print(f"==> {INDEX_ADDR}: GCP にも state にも存在しない — 初回 deploy 扱いで skip")

    return imported
