"""Local alternative to .github/workflows/deploy-api.yml (Phase 6 / GKE).

Builds the search-api image via Cloud Build, pushes to Artifact Registry,
then patches the GKE Deployment (`deployment/search-api` in namespace
`search`) to roll the new image.

Safety rules:
- never delete tags before push;
- always build/deploy an immutable tag (`<sha>-<epoch>`);
- fail fast with diagnostics when Cloud Build / kubectl rollout fails.

**過去事故の再発検知用ログ**:

* Phase 5 Run 2-3 で Cloud Build timeout / Docker COPY 欠落により deploy が
  長時間詰まった時、build id や build URL が不明で `gcloud builds log` を
  手で打つハメになった。ここでは build_id / build URL / 各 phase の経過時刻を
  逐次出力するので、`gcloud builds log <id>` に貼れる情報が常に生 log に残る。
* Phase 5 Run 8 で Cloud Run 0 ログ CrashLoopBackOff の時に `/readyz` 結果と
  revision 切替えの見分けが付かず詰まった。Phase 6 は GKE なので
  `kubectl rollout status` + 失敗時は `kubectl get pods` / `kubectl describe`
  / `kubectl logs` を dump する。
* kubectl context 不一致は毎回の学習 PDCA で 1 位級の詰まりどころ。起動時に
  必ず `current-context` を echo する。
"""

from __future__ import annotations

import subprocess
import sys
import time

from scripts._common import env, resolve_git_sha, run, submit_cloud_build_async, wait_cloud_build

BUILD_TIMEOUT_SEC = 1800
ROLLOUT_TIMEOUT_SEC = 300
NAMESPACE = "search"
DEPLOYMENT = "search-api"
CONTAINER = "search-api"


def _step(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def _info(msg: str) -> None:
    print(f"[info] {msg}", flush=True)


def _error(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr, flush=True)


def _diag(label: str, proc: subprocess.CompletedProcess[str]) -> None:
    _error(f"---- diag {label} exit={proc.returncode} ----")
    if proc.stdout:
        sys.stderr.write(proc.stdout)
        if not proc.stdout.endswith("\n"):
            sys.stderr.write("\n")
    if proc.stderr:
        sys.stderr.write(proc.stderr)
        if not proc.stderr.endswith("\n"):
            sys.stderr.write("\n")
    sys.stderr.flush()


def _require(name: str) -> str:
    value = env(name)
    if not value:
        raise SystemExit(f"[error] required env var {name} is empty")
    return value


def _ensure_kubectl_context(cluster_name: str, region: str, project_id: str) -> None:
    # Phase 7 Run 5 — destroy-all → deploy-all で cluster を同じ name で
    # 再作成すると、kubeconfig には旧 cluster の CA / endpoint が残る一方で
    # context name は一致してしまうため、early-return すると ``kubectl apply``
    # が ``x509: certificate signed by unknown authority`` で失敗する。
    # 毎回 ``gcloud container clusters get-credentials`` を呼んで kubeconfig を
    # 上書きする (値が同じなら no-op に近い fast path)。
    proc = run(["kubectl", "config", "current-context"], capture=True, check=False)
    current = (proc.stdout or "").strip()
    _info(f"kubectl current-context={current!r}")
    _info(
        f"refreshing credentials via `gcloud container clusters get-credentials "
        f"{cluster_name} --region={region}` (avoid stale CA after destroy/recreate)"
    )
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
    after = run(["kubectl", "config", "current-context"], capture=True, check=False)
    _info(f"kubectl current-context now={after.stdout.strip()!r}")


def _dump_rollout_diagnostics() -> None:
    _error(f"---- rollout diagnostics for deployment/{DEPLOYMENT} (namespace={NAMESPACE}) ----")
    for cmd in (
        ["kubectl", "get", "deployment", DEPLOYMENT, f"--namespace={NAMESPACE}", "-o", "wide"],
        [
            "kubectl",
            "get",
            "pods",
            f"--namespace={NAMESPACE}",
            "-l",
            f"app.kubernetes.io/name={DEPLOYMENT}",
            "-o",
            "wide",
        ],
        ["kubectl", "describe", "deployment", DEPLOYMENT, f"--namespace={NAMESPACE}"],
        [
            "kubectl",
            "get",
            "events",
            f"--namespace={NAMESPACE}",
            "--sort-by=.lastTimestamp",
        ],
        [
            "kubectl",
            "logs",
            f"--namespace={NAMESPACE}",
            "-l",
            f"app.kubernetes.io/name={DEPLOYMENT}",
            "--tail=200",
            "--all-containers=true",
        ],
    ):
        _error(f"$ {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.stdout:
            sys.stderr.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        sys.stderr.flush()


def main() -> int:
    project_id = _require("PROJECT_ID")
    region = env("REGION", "asia-northeast1")
    cluster_name = env("GKE_CLUSTER_NAME", "hybrid-search")
    artifact_repo = env("ARTIFACT_REPO_ID", "mlops")
    sha = resolve_git_sha()

    image_tag = f"{sha}-{int(time.time())}"
    image_uri = f"{region}-docker.pkg.dev/{project_id}/{artifact_repo}/search-api:{image_tag}"

    _step(
        f"deploy-api-gke start project={project_id} region={region} "
        f"cluster={cluster_name} repo={artifact_repo}"
    )
    _info(f"image_uri={image_uri}")

    _step("[1/4] ensure kubectl context")
    _ensure_kubectl_context(cluster_name, region, project_id)

    _step("[2/4] Cloud Build submit (async)")
    build_id = submit_cloud_build_async(
        project_id=project_id,
        config="infra/run/services/search_api/cloudbuild.yaml",
        substitutions=f"_IMAGE_URI={image_uri}",
    )
    build_url = (
        f"https://console.cloud.google.com/cloud-build/builds/{build_id}?project={project_id}"
    )
    _info(f"build_id={build_id}")
    _info(f"build_url={build_url}")
    _info(f"tail via: gcloud builds log {build_id} --project={project_id} --stream")

    _step(f"[3/4] Cloud Build wait (timeout={BUILD_TIMEOUT_SEC}s)")
    build_start = time.monotonic()
    try:
        wait_cloud_build(
            project_id=project_id,
            build_id=build_id,
            timeout_sec=BUILD_TIMEOUT_SEC,
        )
    except Exception:
        _error(
            f"Cloud Build FAILED build_id={build_id} build_url={build_url} "
            f"elapsed={(time.monotonic() - build_start):.0f}s"
        )
        raise
    _info(f"Cloud Build SUCCESS elapsed={(time.monotonic() - build_start):.0f}s")

    _step(f"[4/4] kubectl set image + rollout status (timeout={ROLLOUT_TIMEOUT_SEC}s)")
    _info(
        f"kubectl set image deployment/{DEPLOYMENT} {CONTAINER}={image_uri} --namespace={NAMESPACE}"
    )
    run(
        [
            "kubectl",
            "set",
            "image",
            f"deployment/{DEPLOYMENT}",
            f"{CONTAINER}={image_uri}",
            f"--namespace={NAMESPACE}",
        ]
    )
    rollout_start = time.monotonic()
    proc = run(
        [
            "kubectl",
            "rollout",
            "status",
            f"deployment/{DEPLOYMENT}",
            f"--namespace={NAMESPACE}",
            f"--timeout={ROLLOUT_TIMEOUT_SEC}s",
        ],
        capture=True,
        check=False,
    )
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        _diag("kubectl rollout status", proc)
        _dump_rollout_diagnostics()
        _error(
            f"rollout FAILED image={image_uri} elapsed={(time.monotonic() - rollout_start):.0f}s"
        )
        return 1
    _info(f"rollout SUCCESS image={image_uri} elapsed={(time.monotonic() - rollout_start):.0f}s")
    _step(f"deploy-api-gke DONE image={image_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
