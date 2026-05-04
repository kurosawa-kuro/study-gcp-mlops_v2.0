"""Local-build alternative to scripts.deploy.api_gke (Phase 7 GKE).

Builds the search-api image with local `docker buildx` (BuildKit) and pushes
to Artifact Registry, then patches the GKE Deployment exactly like
scripts.deploy.api_gke does. The only differences from api_gke.py:

1. Build runs on the developer's machine using `docker buildx build --push`,
   so BuildKit `--mount=type=cache` mounts in the Dockerfile actually
   accelerate iterative builds (Cloud Build's docker daemon doesn't share
   cache between invocations).
2. The first build is bottlenecked by the developer's upstream bandwidth
   (3GB image push from WSL2 etc.); 2nd+ builds with cached uv wheels and
   unchanged source typically finish in 1-3 minutes total.

Use `make deploy-api-local` to invoke this. CI / shared-runner deploys
should keep using `make deploy-api` (Cloud Build with kaniko cache).

Pre-reqs (validated up-front so failure is loud):
- `docker buildx` available (BuildKit enabled by default in modern Docker).
- `gcloud auth configure-docker <region>-docker.pkg.dev` previously run, OR
  `gcloud` CLI logged in (we run `configure-docker` ourselves on first call).
- kubectl context pointed at the target GKE cluster (auto-fetched).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

from scripts._common import env, resolve_git_sha, run

ROLLOUT_TIMEOUT_SEC = 300
NAMESPACE = "search"
DEPLOYMENT = "search-api"
CONTAINER = "search-api"
DOCKERFILE = "infra/run/services/search_api/Dockerfile"


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


def _ensure_docker_buildx() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("[error] docker CLI not found — install Docker Desktop / docker-ce first")
    proc = subprocess.run(
        ["docker", "buildx", "version"], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise SystemExit(
            "[error] `docker buildx` not available. Install BuildKit (Docker Desktop ≥ 19.03 "
            "or `docker buildx install` plugin)."
        )


def _ensure_ar_auth(region: str) -> None:
    """Idempotent: configures local docker to push to <region>-docker.pkg.dev via gcloud."""
    registry = f"{region}-docker.pkg.dev"
    proc = subprocess.run(
        ["gcloud", "auth", "configure-docker", registry, "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        _diag("gcloud auth configure-docker", proc)
        raise SystemExit(
            f"[error] `gcloud auth configure-docker {registry}` failed — run "
            "`gcloud auth login` first."
        )


def _ensure_kubectl_context(cluster_name: str, region: str, project_id: str) -> None:
    # Phase 7 Run 5 — destroy-all → deploy-all で cluster を再作成すると
    # kubeconfig 上の context name は同じでも CA / endpoint が古いままになるため、
    # 毎回 get-credentials を呼んで kubeconfig を上書きする (no-op に近い fast path)。
    proc = run(["kubectl", "config", "current-context"], capture=True, check=False)
    if proc.stdout:
        _info(f"current-context={proc.stdout.strip()}")
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


def main() -> int:
    project_id = _require("PROJECT_ID")
    region = env("REGION", "asia-northeast1")
    cluster_name = env("GKE_CLUSTER_NAME", "hybrid-search")
    artifact_repo = env("ARTIFACT_REPO_ID", "mlops")
    sha = resolve_git_sha()

    image_tag = f"{sha}-{int(time.time())}"
    image_uri = f"{region}-docker.pkg.dev/{project_id}/{artifact_repo}/search-api:{image_tag}"

    _step(
        f"deploy-api-gke-local start project={project_id} region={region} "
        f"cluster={cluster_name} repo={artifact_repo}"
    )
    _info(f"image_uri={image_uri}")

    _step("[1/4] ensure docker buildx + AR auth + kubectl context")
    _ensure_docker_buildx()
    _ensure_ar_auth(region)
    _ensure_kubectl_context(cluster_name, region, project_id)

    _step("[2/4] docker buildx build --push (local BuildKit + uv cache mount)")
    build_start = time.monotonic()
    # `--push` 直接 AR に push する (load + push の 2 段階を避ける)。
    # `DOCKER_BUILDKIT=1` env は buildx で常に on。
    proc = subprocess.run(
        [
            "docker",
            "buildx",
            "build",
            "--file",
            DOCKERFILE,
            "--tag",
            image_uri,
            "--push",
            ".",
        ],
        check=False,
    )
    if proc.returncode != 0:
        _error(f"docker buildx build FAILED elapsed={(time.monotonic() - build_start):.0f}s")
        return 1
    _info(f"docker buildx build SUCCESS elapsed={(time.monotonic() - build_start):.0f}s")

    _step(f"[3/4] kubectl set image (namespace={NAMESPACE} deployment={DEPLOYMENT})")
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

    _step(f"[4/4] kubectl rollout status (timeout={ROLLOUT_TIMEOUT_SEC}s)")
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
        _error(
            f"rollout FAILED image={image_uri} elapsed={(time.monotonic() - rollout_start):.0f}s"
        )
        return 1
    _info(f"rollout SUCCESS image={image_uri} elapsed={(time.monotonic() - rollout_start):.0f}s")
    _step(f"deploy-api-gke-local DONE image={image_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
