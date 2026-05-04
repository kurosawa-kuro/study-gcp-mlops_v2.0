"""Build composer-runner image via Cloud Build (Phase 7 V5 fix, 2026-05-03)。

`make build-composer-runner` のラッパー。Cloud Build に kaniko で image を
build させて Artifact Registry に push する。DAG が KubernetesPodOperator から
`python -m <module>` を呼ぶ runner image。

過去 incident: 過去 session の Claude が DAG を `BashOperator: uv run python -m
scripts.X` で書いたが Composer worker に uv / repo source が無く task SUCCEEDED
未達。本 image はこの真因を fix する (V5、TASKS_ROADMAP §4.1)。
"""

from __future__ import annotations

import sys
import time

from scripts._common import env, resolve_git_sha, submit_cloud_build_async, wait_cloud_build

BUILD_TIMEOUT_SEC = 1800

IMAGE_NAME = "composer-runner"
CLOUD_BUILD_CONFIG = "infra/run/services/composer_runner/cloudbuild.yaml"


def _step(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def _info(msg: str) -> None:
    print(f"[info] {msg}", flush=True)


def _error(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr, flush=True)


def _require(name: str) -> str:
    value = env(name)
    if not value:
        raise SystemExit(f"[error] required env var {name} is empty")
    return value


def main() -> int:
    project_id = _require("PROJECT_ID")
    region = env("REGION", "asia-northeast1")
    artifact_repo = env("ARTIFACT_REPO_ID", "mlops")
    sha = resolve_git_sha()

    image_tag = f"{sha}-{int(time.time())}"
    image_uri = f"{region}-docker.pkg.dev/{project_id}/{artifact_repo}/{IMAGE_NAME}:{image_tag}"

    _step(f"build-composer-runner start project={project_id} region={region} repo={artifact_repo}")
    _info(f"image_uri={image_uri}")

    _step("[1/2] Cloud Build submit (async)")
    build_id = submit_cloud_build_async(
        project_id=project_id,
        config=CLOUD_BUILD_CONFIG,
        substitutions=f"_IMAGE_URI={image_uri}",
    )
    build_url = (
        f"https://console.cloud.google.com/cloud-build/builds/{build_id}?project={project_id}"
    )
    _info(f"build_id={build_id}")
    _info(f"build_url={build_url}")
    _info(f"tail via: gcloud builds log {build_id} --project={project_id} --stream")

    _step(f"[2/2] Cloud Build wait (timeout={BUILD_TIMEOUT_SEC}s)")
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

    # latest tag を mutable な「現在の本線 image」として AR の "latest" に張り直す。
    # DAG 側は :latest を pin することで毎回 build で URL を書き換えなくて済む。
    latest_uri = f"{region}-docker.pkg.dev/{project_id}/{artifact_repo}/{IMAGE_NAME}:latest"
    _step(f"[bonus] tag {image_uri} as :latest ({latest_uri})")
    import subprocess

    proc = subprocess.run(
        [
            "gcloud",
            "artifacts",
            "docker",
            "tags",
            "add",
            image_uri,
            latest_uri,
            f"--project={project_id}",
        ],
        check=False,
    )
    if proc.returncode != 0:
        _error(f"latest tag failed (continuing): exit={proc.returncode}")
    else:
        _info(f"latest tag added: {latest_uri}")

    _step(f"build-composer-runner DONE immutable={image_uri} latest={latest_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
