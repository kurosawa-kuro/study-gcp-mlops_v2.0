"""kubeconfig synchronisation for the target GKE cluster.

`terraform apply` がクラスタを作成しても、ローカル kubeconfig が自動で
その cluster を指すわけではない。apply-manifests / overlay-configmap は
`kubectl` を直叩きするため、先に `gcloud container clusters get-credentials`
を流して `current-context` を target cluster に固定する。

Phase 7 Run 5 教訓 — `destroy-all → deploy-all` PDCA loop では cluster を
同じ name で再作成するが、古い kubeconfig には旧 cluster の CA cert +
endpoint IP が残ったまま、context name だけが一致してしまう。これを
skip 条件として `current-context` 一致で early-return すると、次の
`kubectl apply` が `x509: certificate signed by unknown authority` で
fail する。そのため context 一致による skip はせず、**毎回
get-credentials を呼んで kubeconfig を上書き**する (gcloud 側で値が
同じなら no-op に近い fast path、context 一致でも CA / endpoint は
再フェッチして TLS 不一致を解消する)。
"""

from __future__ import annotations

import subprocess
import time

from scripts._common import env, run
from scripts.lib.gcp_resources import GKE_CLUSTER_NAME_DEFAULT


def ensure() -> None:
    """Refresh kubeconfig to target the freshly-provisioned GKE cluster."""
    project_id = env("PROJECT_ID")
    region = env("REGION", "asia-northeast1")
    cluster_name = env("GKE_CLUSTER_NAME", GKE_CLUSTER_NAME_DEFAULT)
    print(f"==> get-credentials cluster={cluster_name} region={region} project={project_id}")
    run(
        [
            "gcloud",
            "container",
            "clusters",
            "get-credentials",
            cluster_name,
            f"--region={region}",
            f"--project={project_id}",
        ]
    )


def wait_until_api_ready(*, timeout_seconds: int = 600, poll_seconds: int = 10) -> None:
    """Poll the Kubernetes API until the freshly-created cluster answers.

    `get-credentials` can succeed before the control plane is fully reachable.
    `terraform apply` for module.kserve must therefore wait until a trivial
    `kubectl get namespace kube-system` succeeds; otherwise the first apply
    after cluster creation races cert-manager / namespace creation and fails
    with i/o timeout.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        proc = subprocess.run(
            ["kubectl", "get", "namespace", "kube-system", "-o", "name"],
            check=False,
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0 and "namespace/kube-system" in (proc.stdout or ""):
            print("==> kubernetes API reachable (namespace/kube-system)")
            return
        detail = (proc.stderr or proc.stdout or "").strip()
        if detail:
            print(f"==> waiting for kubernetes API: {detail}")
        time.sleep(poll_seconds)
    raise RuntimeError(
        f"kubernetes API did not become reachable within {timeout_seconds}s "
        "(kubectl get namespace kube-system kept failing)"
    )
