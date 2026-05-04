"""Build the Phase 7 custom KServe-side images and roll them onto the cluster.

Two images live in the cluster's ``kserve-inference`` namespace:

1. **property-encoder** — ``ml.serving.encoder`` Vertex CPR FastAPI server
   (multilingual-e5). Deployed via a KServe ``InferenceService``; its
   ``spec.predictor.containers[0].image`` is a placeholder
   (``gcr.io/cloudrun/hello`` in the manifest) until this script patches it.

2. **property-reranker-explain** — ``ml.serving.reranker`` Vertex CPR
   FastAPI server with TreeSHAP ``/explain``. Deployed via a plain
   Kubernetes ``Deployment`` (the KServe stock lgbserver runtime is used for
   ``/predict``; this Pod handles only the explain path). Its image is
   patched via ``kubectl set image`` instead of an ISVC patch because the
   manifest is a plain Deployment, not an InferenceService.

Phase 7 Run 1 incident:

    `make deploy-all` did not include any image build step for these two
    images, so on a fresh project the encoder ISVC came up running
    ``gcr.io/cloudrun/hello`` (a Cloud Run example image returning HTML).
    ``KServeEncoder.embed`` then raised
    ``RuntimeError: KServe encoder.embed returned non-JSON response``
    on the first ``/search`` call.

This script closes that gap: it submits both Cloud Builds (in sequence —
parallelization is a future micro-optimization), waits for ``SUCCESS``,
then patches the cluster so the new digests are picked up.

Idempotency: re-running this script always builds *new* immutable
``<sha>-<epoch>`` tags and patches the cluster accordingly. That matches
the search-api ``deploy-api`` script's convention so ``deploy-all`` is
re-runnable without surprises.
"""

from __future__ import annotations

import sys
import time

from scripts._common import (
    env,
    resolve_git_sha,
    run,
    submit_cloud_build_async,
    wait_cloud_build,
)

BUILD_TIMEOUT_SEC = 1800
NAMESPACE = "kserve-inference"


def _step(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def _info(msg: str) -> None:
    print(f"[info] {msg}", flush=True)


def _error(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr, flush=True)


def _build_image(
    *,
    project_id: str,
    region: str,
    artifact_repo: str,
    image_name: str,
    cloudbuild_path: str,
    sha: str,
) -> str:
    """Submit a Cloud Build that pushes ``<region>-...:<sha>-<epoch>`` and wait."""
    image_tag = f"{sha}-{int(time.time())}"
    image_uri = f"{region}-docker.pkg.dev/{project_id}/{artifact_repo}/{image_name}:{image_tag}"
    _step(f"Cloud Build submit image={image_uri} config={cloudbuild_path}")
    build_id = submit_cloud_build_async(
        project_id=project_id,
        config=cloudbuild_path,
        substitutions=f"_IMAGE_URI={image_uri}",
    )
    build_url = (
        f"https://console.cloud.google.com/cloud-build/builds/{build_id}?project={project_id}"
    )
    _info(f"build_id={build_id}")
    _info(f"build_url={build_url}")
    _info(f"tail via: gcloud builds log {build_id} --project={project_id} --stream")

    started = time.monotonic()
    try:
        wait_cloud_build(project_id=project_id, build_id=build_id, timeout_sec=BUILD_TIMEOUT_SEC)
    except Exception:
        _error(
            f"Cloud Build FAILED build_id={build_id} build_url={build_url} "
            f"elapsed={(time.monotonic() - started):.0f}s"
        )
        raise
    _info(f"Cloud Build SUCCESS image={image_uri} elapsed={(time.monotonic() - started):.0f}s")
    return image_uri


def _patch_inference_service_image(isvc_name: str, image_uri: str) -> None:
    """Patch ``spec.predictor.containers[0].image`` on a KServe ISVC."""
    patch = (
        '{"spec":{"predictor":{"containers":[{'
        '"name":"kserve-container",'
        f'"image":"{image_uri}"'
        "}]}}}"
    )
    _step(f"kubectl patch inferenceservice/{isvc_name} image={image_uri}")
    run(
        [
            "kubectl",
            "patch",
            "inferenceservice",
            isvc_name,
            f"--namespace={NAMESPACE}",
            "--type=merge",
            f"--patch={patch}",
        ]
    )


def _set_deployment_image(deployment: str, container: str, image_uri: str) -> None:
    """Patch a plain Deployment's container image (used for reranker-explain)."""
    _step(f"kubectl set image deployment/{deployment} {container}={image_uri} -n {NAMESPACE}")
    run(
        [
            "kubectl",
            "set",
            "image",
            f"deployment/{deployment}",
            f"{container}={image_uri}",
            f"--namespace={NAMESPACE}",
        ]
    )


def main() -> int:
    project_id = env("PROJECT_ID")
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")
    region = env("REGION", "asia-northeast1")
    artifact_repo = env("ARTIFACT_REPO_ID", "mlops")
    sha = resolve_git_sha()

    _step(
        f"build_kserve_images start project={project_id} region={region} "
        f"repo={artifact_repo} sha={sha}"
    )

    encoder_image = _build_image(
        project_id=project_id,
        region=region,
        artifact_repo=artifact_repo,
        image_name="property-encoder",
        cloudbuild_path="infra/run/services/encoder/cloudbuild.yaml",
        sha=sha,
    )
    reranker_image = _build_image(
        project_id=project_id,
        region=region,
        artifact_repo=artifact_repo,
        image_name="property-reranker",
        cloudbuild_path="infra/run/services/reranker/cloudbuild.yaml",
        sha=sha,
    )

    _patch_inference_service_image("property-encoder", encoder_image)
    _set_deployment_image("property-reranker-explain", "reranker", reranker_image)

    _step(f"build_kserve_images DONE encoder={encoder_image} reranker_explain={reranker_image}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
