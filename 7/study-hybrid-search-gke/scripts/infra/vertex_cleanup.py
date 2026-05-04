"""Vertex AI Endpoint cleanup helpers for destroy-all.

Terraform-managed `google_vertex_ai_endpoint` は empty shell。
`aiplatform.Model.deploy()` (KFP components / scripts) が server-side で
`deployedModels` を埋めるため、Terraform 側からは見えない。残っていると
`terraform destroy` が HTTP 400 ``Endpoint has deployed or being-deployed
DeployedModel(s)`` で fail するので、本 module で undeploy する。

Phase 7 では KServe に serving 移譲しており Vertex Endpoint は完全に
shell として残置 — ただし Phase 6 までの canonical 経路を継承する設計上、
リソースとしては存在する (`scripts/lib/gcp_resources.VERTEX_ENDPOINTS`)。
"""

from __future__ import annotations

import json
import subprocess
import time

from scripts._common import env, run
from scripts.lib.gcp_resources import VERTEX_ENDPOINTS


def undeploy_endpoint_models(project_id: str, region: str, endpoint: str) -> None:
    """Synchronously undeploy every DeployedModel on one endpoint.

    Benign when the endpoint does not exist yet (fresh project / already
    torn down) — we detect that via `gcloud describe` returning non-zero.
    `gcloud ... undeploy-model --quiet` waits for the long-running op,
    so control returns only when the deployed_model is fully detached.
    """
    proc = subprocess.run(
        [
            "gcloud",
            "ai",
            "endpoints",
            "describe",
            endpoint,
            f"--region={region}",
            f"--project={project_id}",
            "--format=json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"    endpoint {endpoint!r} not present — skip")
        return
    payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    deployed = payload.get("deployedModels") or []
    if not deployed:
        print(f"    endpoint {endpoint!r} has no deployed_models — skip")
        return
    for dm in deployed:
        dm_id = dm["id"]
        display = dm.get("displayName", "?")
        print(f"    undeploy-model {endpoint} id={dm_id} display={display}")
        run(
            [
                "gcloud",
                "ai",
                "endpoints",
                "undeploy-model",
                endpoint,
                f"--deployed-model-id={dm_id}",
                f"--region={region}",
                f"--project={project_id}",
                "--quiet",
            ]
        )


def undeploy_all_endpoint_shells(project_id: str | None = None, region: str | None = None) -> None:
    """Iterate `VERTEX_ENDPOINTS` and detach all DeployedModels."""
    pid = project_id or env("PROJECT_ID")
    rgn = region or env("VERTEX_LOCATION") or env("REGION")
    for endpoint in VERTEX_ENDPOINTS:
        undeploy_endpoint_models(pid, rgn, endpoint)


def deployed_index_exists(project_id: str, region: str, deployed_index_id: str) -> bool:
    """Return True when any Vertex Vector Search endpoint still has the ID deployed."""
    return deployed_index_state(project_id, region, deployed_index_id) != "absent"


def deployed_index_state(project_id: str, region: str, deployed_index_id: str) -> str:
    """Classify the deployed_index lifecycle state:

    - ``"absent"`` — no DeployedIndex with that ID across any endpoint.
    - ``"ready"`` — DeployedIndex exists and has ``indexSyncTime`` set
      (fully attached and serving — terraform apply is idempotent here, so
      ``wait_for_deployed_index_absent`` can early-exit on resume after a
      partial deploy-all failure).
    - ``"transitional"`` — DeployedIndex exists but has no ``indexSyncTime``
      yet (being-undeployed ghost from prior destroy / mid-attach). Callers
      must keep waiting for this to clear before re-applying.
    """
    proc = subprocess.run(
        [
            "gcloud",
            "ai",
            "index-endpoints",
            "list",
            f"--region={region}",
            f"--project={project_id}",
            "--format=json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        print(f"    index-endpoints list failed — assume absent and continue: {detail}")
        return "absent"
    payload = json.loads(proc.stdout) if proc.stdout.strip() else []
    for endpoint in payload:
        deployed = endpoint.get("deployedIndexes") or []
        for idx in deployed:
            if idx.get("id") == deployed_index_id:
                return "ready" if idx.get("indexSyncTime") else "transitional"
    return "absent"


def undeploy_all_vvs_deployed_indexes(
    project_id: str | None = None, region: str | None = None
) -> None:
    """Proactively undeploy ALL Vertex Vector Search deployed indexes before destroy.

    `deploy-all` の `wait_for_deployed_index_absent` は **wait** しかしないので、
    前 PDCA cycle で `destroy-all` が deployed index を残したまま終わると、次回
    `make deploy-all` が step 6 (tf-apply stage1) で 15 分待った末に
    timeout で fail する事故が起きる。

    本 helper は `destroy-all` 時点で「endpoint に attach されている全
    deployed index を能動的に undeploy する」ことで PDCA reproducibility を
    保証する (= 「何度叩いても通る」契約の一部)。

    benign on no-state: index endpoints が存在しない / deployed indexes 0 件
    のときは何もしない。`gcloud ... undeploy-index --quiet` は long-running
    operation を同期的に待つ。
    """
    pid = project_id or env("PROJECT_ID")
    rgn = region or env("VERTEX_LOCATION") or env("REGION")

    proc = subprocess.run(
        [
            "gcloud",
            "ai",
            "index-endpoints",
            "list",
            f"--region={rgn}",
            f"--project={pid}",
            "--format=json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        print(f"    index-endpoints list failed — assume absent and continue: {detail}")
        return
    endpoints = json.loads(proc.stdout) if proc.stdout.strip() else []
    if not endpoints:
        print("    no Vector Search index endpoints — skip")
        return

    for endpoint in endpoints:
        endpoint_name = endpoint.get("name", "")
        endpoint_id = endpoint_name.rsplit("/", 1)[-1] if endpoint_name else ""
        if not endpoint_id:
            continue
        deployed = endpoint.get("deployedIndexes") or []
        if not deployed:
            print(f"    index-endpoint {endpoint_id} has no deployed indexes — skip")
            continue
        for idx in deployed:
            deployed_id = idx.get("id")
            if not deployed_id:
                continue
            print(f"    undeploy-index endpoint={endpoint_id} deployed_index_id={deployed_id}")
            run(
                [
                    "gcloud",
                    "ai",
                    "index-endpoints",
                    "undeploy-index",
                    endpoint_id,
                    f"--deployed-index-id={deployed_id}",
                    f"--region={rgn}",
                    f"--project={pid}",
                    "--quiet",
                ]
            )


def wait_for_deployed_index_absent(
    project_id: str,
    region: str,
    deployed_index_id: str,
    *,
    timeout_seconds: int = 900,
    poll_seconds: int = 15,
) -> None:
    """Poll until VVS deployed index reaches a state safe for `terraform apply`.

    Two safe states (early-exit):

    - ``absent`` — fresh deploy after destroy-all completed cleanly.
    - ``ready`` — DeployedIndex already attached and ``indexSyncTime`` set
      (resume scenario after a partial deploy-all failure; terraform apply
      is idempotent for the unchanged Vector Search module).

    Unsafe / transitional state (keep waiting):

    - ``transitional`` — DeployedIndex present but no ``indexSyncTime`` (the
      ghost ``being undeployed`` state after destroy-all, or mid-attach).
      Re-applying here causes HTTP 400 from Vertex; we must wait it out.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = deployed_index_state(project_id, region, deployed_index_id)
        if state in ("absent", "ready"):
            print(f"==> VVS deployed_index_id {deployed_index_id!r} state={state} — proceed")
            return
        print(
            f"==> waiting for transitional VVS deployed_index_id {deployed_index_id!r} "
            f"(state={state}) to settle"
        )
        time.sleep(poll_seconds)
    raise RuntimeError(
        f"Vertex Vector Search deployed_index_id {deployed_index_id!r} still transitional after "
        f"{timeout_seconds}s; previous undeploy/delete likely still in progress"
    )
