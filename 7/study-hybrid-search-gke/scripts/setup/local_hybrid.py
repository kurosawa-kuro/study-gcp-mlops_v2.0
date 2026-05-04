"""Start the local hybrid-search stack with one command.

What this does:

1. resolve non-secret config from ``env/config/setting.yaml``
2. resolve local secrets from ``env/secret/credential.yaml`` (fallback:
   Secret Manager via gcloud)
3. ensure a synthetic LightGBM model exists for the local reranker
4. boot:
   - local encoder server
   - local reranker server
   - local app server

This keeps the local startup path aligned with the production app contract:
the app still talks to KServe-like HTTP endpoints, but the endpoints are
provided by local dev servers instead of cluster-local Services.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from scripts._common import env, gcloud, run, secret
from scripts.lib.gcp_resources import MEILI_SERVICE_NAME_DEFAULT


def _log(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def _require(name: str, value: str) -> str:
    if not value.strip():
        raise SystemExit(f"[error] required value {name} is empty")
    return value.strip()


def _resolve_meili_base_url() -> str:
    explicit = env("MEILI_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    service = env("MEILI_SERVICE", MEILI_SERVICE_NAME_DEFAULT)
    return _require(
        "MEILI_BASE_URL",
        gcloud(
            "run",
            "services",
            "describe",
            service,
            f"--project={env('PROJECT_ID')}",
            f"--region={env('REGION')}",
            "--format=value(status.url)",
            capture=True,
        ),
    ).rstrip("/")


def _resolve_meili_master_key() -> str:
    local_value = secret("MEILI_MASTER_KEY")
    if local_value:
        return local_value
    secret_id = env("MEILI_MASTER_KEY_SECRET_ID", "meili-master-key")
    return _require(
        "MEILI_MASTER_KEY",
        gcloud(
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={secret_id}",
            f"--project={env('PROJECT_ID')}",
            capture=True,
        ),
    )


def _ensure_local_reranker_model(model_path: Path) -> None:
    if model_path.exists() and model_path.stat().st_size > 0:
        _log(f"reuse local reranker model {model_path}")
        return
    model_path.parent.mkdir(parents=True, exist_ok=True)
    _log(f"build synthetic reranker model {model_path}")
    run(
        ["uv", "run", "rank-train", "--dry-run", "--save-to", str(model_path)],
        check=True,
    )


def _wait_http(url: str, *, timeout_sec: float = 120.0) -> None:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if 200 <= resp.status < 500:
                    return
        except urllib.error.URLError:
            time.sleep(0.5)
    raise SystemExit(f"[error] startup timeout waiting for {url}")


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _spawn(cmd: list[str], *, child_env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(cmd, env=child_env)


def main() -> int:
    project_id = env("PROJECT_ID")
    encoder_port = env("LOCAL_ENCODER_PORT", "18081")
    reranker_port = env("LOCAL_RERANKER_PORT", "18082")
    app_port = env("LOCAL_API_PORT", "8000")
    meili_base_url = _resolve_meili_base_url()
    meili_master_key = _resolve_meili_master_key()
    model_path = Path(
        env("LOCAL_RERANKER_MODEL_PATH", "/tmp/hybrid-search-cloud-smoke-model.txt")
    ).expanduser()
    impersonate_sa = env(
        "MEILI_IMPERSONATE_SERVICE_ACCOUNT",
        f"sa-api@{project_id}.iam.gserviceaccount.com" if project_id else "",
    ).strip()

    for label, port_str in (
        ("encoder", encoder_port),
        ("reranker", reranker_port),
        ("app", app_port),
    ):
        port = int(port_str)
        if _port_in_use(port):
            raise SystemExit(
                f"[error] local {label} port {port} is already in use. "
                "Stop the existing process or override LOCAL_*_PORT."
            )

    _ensure_local_reranker_model(model_path)

    base_env = os.environ.copy()
    base_env.setdefault("UV_CACHE_DIR", "/tmp/uv-cache")

    encoder_env = base_env | {
        "HOST": "127.0.0.1",
        "AIP_HTTP_PORT": encoder_port,
    }
    reranker_env = base_env | {
        "HOST": "127.0.0.1",
        "AIP_HTTP_PORT": reranker_port,
        "LOCAL_RERANKER_MODEL_PATH": str(model_path),
    }
    app_env = base_env | {
        "ENABLE_SEARCH": "true",
        "ENABLE_RERANK": "true",
        "KSERVE_ENCODER_URL": f"http://127.0.0.1:{encoder_port}/predict",
        "KSERVE_RERANKER_URL": f"http://127.0.0.1:{reranker_port}/predict",
        "KSERVE_RERANKER_EXPLAIN_URL": f"http://127.0.0.1:{reranker_port}/explain",
        "MEILI_BASE_URL": meili_base_url,
        "MEILI_MASTER_KEY": meili_master_key,
        "MEILI_IMPERSONATE_SERVICE_ACCOUNT": impersonate_sa,
    }

    processes: list[subprocess.Popen[str]] = []
    try:
        _log("start local encoder")
        processes.append(
            _spawn(["uv", "run", "python", "-m", "ml.serving.encoder"], child_env=encoder_env)
        )
        _wait_http(f"http://127.0.0.1:{encoder_port}/health")

        _log("start local reranker")
        processes.append(
            _spawn(["uv", "run", "python", "-m", "ml.serving.reranker"], child_env=reranker_env)
        )
        _wait_http(f"http://127.0.0.1:{reranker_port}/health")

        _log("start local app")
        processes.append(
            _spawn(
                [
                    "uv",
                    "run",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    app_port,
                ],
                child_env=app_env,
            )
        )
        _wait_http(f"http://127.0.0.1:{app_port}/healthz")
        _log(
            f"local hybrid stack READY app=http://127.0.0.1:{app_port} "
            f"encoder=http://127.0.0.1:{encoder_port} reranker=http://127.0.0.1:{reranker_port}"
        )

        app_proc = processes[-1]
        while True:
            rc = app_proc.poll()
            if rc is not None:
                return rc
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 130
    finally:
        for proc in reversed(processes):
            if proc.poll() is not None:
                continue
            proc.send_signal(signal.SIGINT)
        for proc in reversed(processes):
            if proc.poll() is not None:
                continue
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
