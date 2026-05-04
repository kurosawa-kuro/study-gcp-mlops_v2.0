"""Shared helpers for scripts/*.py and scripts/ops/*.py.

Stdlib-only by design (per scripts/README.md). The functions wrap the most
common shell idioms (gcloud subprocess calls, IAM-gated HTTP requests,
env-var defaults) so individual scripts stay short and focused on intent.

**Config split (do not conflate)**:

- ``DEFAULTS`` ← ``env/config/setting.yaml`` — **non-secret values only** by repo
  design (IDs, regions, bucket names). Never store credential material there.
- ``SECRET_DEFAULTS`` ← ``env/secret/credential.yaml`` — **local secrets only**
  (directory gitignored). Production uses Secret Manager.

The YAML parser is a deliberately minimal hand-rolled parser that supports only
top-level flat key:value entries and block-style lists (no PyYAML dependency).
See ``env/README.md``.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "env" / "config" / "setting.yaml"
_SECRET_SETTINGS_PATH = (
    Path(__file__).resolve().parent.parent / "env" / "secret" / "credential.yaml"
)


def _load_flat_yaml(path: Path) -> dict[str, str]:
    """Parse the flat key:value subset of a YAML file.

    Supported syntax: top-level `key: value` lines, `#` comments, blank lines.
    Values may be quoted with `"` or `'`. Anything else (nesting, anchors,
    multiline strings) is intentionally rejected to keep this parser tiny.
    """
    settings: dict[str, str] = {}
    if not path.exists():
        return settings
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        # Skip YAML list markers (lines like `- foo`) and block-style list keys
        # (e.g. `admin_user_emails:` with an empty value followed by `- foo`).
        if key.startswith("-"):
            continue
        if value:
            settings[key.upper()] = value
    return settings


def _load_list_setting(list_key: str) -> list[str]:
    """Read a YAML block-style list from env/config/setting.yaml.

    Supports the shape::

        admin_user_emails:
          - user1@example.com
          - user2@example.com

    Returns [] if the key is absent or has no list items. Quoted strings
    (``"foo"`` / ``'foo'``) are unwrapped. Kept minimal; does not support
    flow-style (`[a, b]`) or nesting.
    """
    if not _SETTINGS_PATH.exists():
        return []
    items: list[str] = []
    in_block = False
    for raw in _SETTINGS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        if not in_block:
            if stripped.strip().startswith(f"{list_key}:"):
                tail = stripped.split(":", 1)[1].strip()
                if tail:
                    # inline form not supported here — bail
                    return []
                in_block = True
            continue
        # in block: accept either `  - value` or break on first non-indented / non-dash line
        if not raw.startswith((" ", "\t")):
            break
        item = stripped.strip()
        if not item.startswith("-"):
            break
        item = item[1:].strip().strip('"').strip("'")
        if item:
            items.append(item)
    return items


DEFAULTS = _load_flat_yaml(_SETTINGS_PATH)
SECRET_DEFAULTS = _load_flat_yaml(_SECRET_SETTINGS_PATH)


def resolve_project_id() -> str:
    """Return GCP project id for SDK / gcloud.

    **GCP (Composer / composer-runner Pod)**: Composer injects ``GCP_PROJECT``.
    Do **not** rely on ``setting.yaml`` for live behavior — change
    ``infra/terraform/modules/composer`` ``env_variables`` if something is missing.

    **Precedence** (first non-empty wins):

    1. ``GCP_PROJECT`` — Composer / GKE standard (canonical on GCP)
    2. ``PROJECT_ID`` — Makefile / CI exports
    3. ``DEFAULTS["PROJECT_ID"]`` from ``setting.yaml`` — **local laptop only**
       when neither env var is set (composer-runner image omits ``setting.yaml``
       on purpose).
    """
    return (
        os.environ.get("GCP_PROJECT", "").strip()
        or os.environ.get("PROJECT_ID", "").strip()
        or DEFAULTS.get("PROJECT_ID", "").strip()
    )


def env(name: str, default: str | None = None) -> str:
    """Read an env var with a project-wide default fallback.

    For ``PROJECT_ID`` and ``GCP_PROJECT``, unset or empty values fall through to
    the other name, then ``default``, then ``DEFAULTS["PROJECT_ID"]`` — see
    :func:`resolve_project_id`.
    """
    if name in ("PROJECT_ID", "GCP_PROJECT"):
        explicit = os.environ.get(name)
        if explicit is not None and str(explicit).strip() != "":
            return str(explicit).strip()
        sibling = "GCP_PROJECT" if name == "PROJECT_ID" else "PROJECT_ID"
        alt = os.environ.get(sibling, "").strip()
        if alt:
            return alt
        if default is not None:
            return str(default).strip() if default else ""
        return DEFAULTS.get("PROJECT_ID", "").strip()
    fallback = default if default is not None else DEFAULTS.get(name, "")
    return os.environ.get(name, fallback)


def secret(name: str, default: str | None = None) -> str:
    """Read a secret env var with credential.yaml fallback."""
    fallback = default if default is not None else SECRET_DEFAULTS.get(name, "")
    return os.environ.get(name, fallback)


def terraform_var_args(*var_names: str) -> list[str]:
    """Build ``-var=KEY=VALUE`` args via env() lookup.

    deploy_all / destroy_all で同じ ``-var=github_repo=...`` リストを独立に
    組み立てており drift 源だった。本 helper に集約することで、新 var
    追加時の更新箇所を 1 つに固定する。``var_names`` は env 名 (大文字)
    で渡し、terraform 側には小文字 ``-var=...`` で出力される。
    """
    return [f"-var={name.lower()}={env(name)}" for name in var_names]


def gcs_bucket_name(suffix: str) -> str:
    """Compose ``<project_id>-<suffix>`` bucket name from PROJECT_ID env.

    seed_lgbm_model.py / upload_encoder_assets.py / destroy_all.py が独自に
    ``f"{project_id}-models"`` 等を組み立てていた重複の集約先。
    """
    return f"{env('PROJECT_ID')}-{suffix}"


def run(
    cmd: list[str], *, capture: bool = False, check: bool = True, timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    """Thin wrapper around subprocess.run. `capture=True` returns stdout in `.stdout`."""
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        timeout=timeout,
    )


def gcloud(*args: str, capture: bool = False) -> str:
    """Invoke gcloud with the supplied args. Returns stripped stdout when capture=True."""
    proc = run(["gcloud", *args], capture=capture)
    return proc.stdout.strip() if capture and proc.stdout else ""


def resolve_git_sha() -> str:
    """Resolve the image-tag SHA without forcing the caller to pre-set ``GIT_SHA``.

    Order: ``$GIT_SHA`` env (CI / explicit override) → ``git rev-parse HEAD``
    (developer machines) → ``dev-<epoch>`` (detached / non-git contexts).
    Phase 7 Run 1 で `make deploy-api` を素で叩いて step 7 が
    ``required env var GIT_SHA is empty`` で fail した教訓から、このヘルパー
    が呼び出し側の hard-fail を吸収する。
    """
    explicit = env("GIT_SHA")
    if explicit:
        return explicit
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=False, text=True, stdout=subprocess.PIPE
    )
    sha = (proc.stdout or "").strip()
    if proc.returncode == 0 and sha:
        return sha
    return f"dev-{int(time.time())}"


def cloud_run_url(service: str | None = None) -> str:
    """Resolve the Cloud Run Service URL via `gcloud run services describe`."""
    svc = service or env("API_SERVICE")
    return gcloud(
        "run",
        "services",
        "describe",
        svc,
        f"--project={env('PROJECT_ID')}",
        f"--region={env('REGION')}",
        "--format=value(status.url)",
        capture=True,
    )


DEFAULT_GATEWAY_NAMESPACE = "search"
DEFAULT_GATEWAY_NAME = "search-api-gateway"
DEFAULT_GATEWAY_HOST_HEADER = "search-api.example.com"


def gateway_url(*, namespace: str | None = None, name: str | None = None) -> str:
    """Resolve the GKE Gateway external URL via kubectl.

    Phase 7 で serving 層が Cloud Run → GKE Gateway に切り替わったため、
    ``cloud_run_url()`` の代わりに `kubectl get gateway` の
    ``status.addresses[0].value`` (= 外部 IP) を ``https://`` 付きで返す。
    HTTPRoute の hostname は IP 直叩きと噛み合わないので、呼び出し側は
    ``Host`` ヘッダで補う前提 (``DEFAULT_GATEWAY_HOST_HEADER``)。
    """
    ns = namespace or env("GATEWAY_NAMESPACE", DEFAULT_GATEWAY_NAMESPACE)
    nm = name or env("GATEWAY_NAME", DEFAULT_GATEWAY_NAME)
    proc = run(
        [
            "kubectl",
            "get",
            "gateway",
            nm,
            f"--namespace={ns}",
            "-o",
            "jsonpath={.status.addresses[0].value}",
        ],
        capture=True,
    )
    addr = (proc.stdout or "").strip()
    if not addr:
        raise RuntimeError(
            f"gateway {ns}/{nm} has no external address yet "
            "(check `kubectl get gateway -n search` for PROGRAMMED=True)"
        )
    return f"https://{addr}"


def identity_token() -> str:
    """Mint an OIDC token for IAM-gated Cloud Run calls."""
    return gcloud("auth", "print-identity-token", capture=True)


@dataclass(frozen=True)
class ResolvedApiTarget:
    """Resolved API endpoint + auth mode for ops scripts.

    Phase 7 で serving が GKE Gateway (IP-based HTTPS + 自己署名 TLS) になり、
    呼び出し側は (a) HTTPRoute の hostname を ``Host`` ヘッダで補完し
    (b) self-signed cert なので TLS 検証を無効化する必要がある。両者を
    `ResolvedApiTarget` の責務に閉じ込めて呼び出し側はモード差を意識しない。
    """

    url: str
    token: str | None
    mode: str
    host_header: str | None = None
    verify_tls: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)

    def call(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        timeout: int = 30,
    ) -> tuple[int, str]:
        """Invoke ``http_json`` with this target's URL prefix and auth context."""
        return http_json(
            method,
            f"{self.url}{path}",
            token=self.token,
            payload=payload,
            timeout=timeout,
            host_header=self.host_header,
            verify_tls=self.verify_tls,
            extra_headers=self.extra_headers or None,
        )


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_api_target() -> ResolvedApiTarget:
    """Resolve the target API base URL + optional Bearer token.

    Supported modes:
    - explicit ``API_URL``: use it as-is. Mint a token only when
      ``API_REQUIRE_TOKEN=true``. ``API_HOST_HEADER`` / ``API_INSECURE_TLS``
      で Host ヘッダ / TLS 検証を上書き可能。``TARGET`` より優先。
    - ``TARGET=local``: use ``LOCAL_API_URL`` and no token
    - ``TARGET=gcp`` (default): resolve the Phase 7 GKE Gateway URL via
      ``gateway_url()``. IAP は dev default で disabled なので no token、
      自己署名 TLS のため ``verify_tls=False``、HTTPRoute と一致させるため
      ``Host: search-api.example.com`` を付与する。
    """
    target = os.environ.get("TARGET", "gcp").strip().lower()
    explicit_url = os.environ.get("API_URL", "").strip().rstrip("/")
    if explicit_url:
        token = identity_token() if _env_flag("API_REQUIRE_TOKEN") else None
        return ResolvedApiTarget(
            url=explicit_url,
            token=token,
            mode="explicit",
            host_header=os.environ.get("API_HOST_HEADER") or None,
            verify_tls=not _env_flag("API_INSECURE_TLS"),
        )
    if target == "local":
        return ResolvedApiTarget(
            url=os.environ.get("LOCAL_API_URL", "http://127.0.0.1:8080").rstrip("/"),
            token=None,
            mode="local",
        )
    if target == "gcp":
        return ResolvedApiTarget(
            url=gateway_url(),
            token=None,
            mode="gcp",
            host_header=os.environ.get("API_HOST_HEADER", DEFAULT_GATEWAY_HOST_HEADER),
            verify_tls=False,
        )
    raise ValueError("TARGET must be either 'local' or 'gcp'")


def http_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict | None = None,
    timeout: int = 30,
    host_header: str | None = None,
    verify_tls: bool = True,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """POST/GET JSON with optional Bearer token. Returns (status_code, body_text).

    ``host_header`` を渡すと ``Host`` ヘッダを上書きする (Phase 7 で IP 直叩き
    + HTTPRoute hostname の組合せに対応)。``verify_tls=False`` で TLS 検証を
    無効化する (自己署名 cert 用)。
    """
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if host_header:
        headers["Host"] = host_header
    if extra_headers:
        headers.update(extra_headers)
    data: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    context: ssl.SSLContext | None = None
    if not verify_tls:
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body


def fail(msg: str, code: int = 1) -> int:
    """Print to stderr and return an exit code (use as `return fail("...")`)."""
    print(msg, file=sys.stderr)
    return code


def print_pretty(body: str) -> None:
    """Best-effort pretty-print of a JSON body (falls back to raw)."""
    try:
        print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(body)


def submit_cloud_build_async(
    *, project_id: str, config: str, substitutions: str, timeout: int | None = None
) -> str:
    """Submit Cloud Build asynchronously and return build id."""
    proc = run(
        [
            "gcloud",
            "builds",
            "submit",
            f"--project={project_id}",
            f"--config={config}",
            f"--substitutions={substitutions}",
            "--async",
            "--format=value(id)",
            ".",
        ],
        capture=True,
        timeout=timeout,
    )
    build_id = (proc.stdout or "").strip()
    if not build_id:
        raise RuntimeError("cloud build submission returned empty build id")
    return build_id


def wait_cloud_build(
    *,
    project_id: str,
    build_id: str,
    timeout_sec: int,
    poll_sec: int = 10,
) -> None:
    """Poll Cloud Build status and fail fast on timeout/failure."""

    def _print_build_diagnostics() -> None:
        try:
            summary = gcloud(
                "builds",
                "describe",
                build_id,
                f"--project={project_id}",
                "--format=value(logUrl,status,createTime,startTime,finishTime)",
                capture=True,
            )
            if summary:
                print(f"[cloud-build] summary: {summary}", file=sys.stderr)
        except Exception as exc:  # pragma: no cover
            print(f"[cloud-build] failed to fetch describe summary: {exc}", file=sys.stderr)

    deadline = time.monotonic() + timeout_sec
    while True:
        status = gcloud(
            "builds",
            "describe",
            build_id,
            f"--project={project_id}",
            "--format=value(status)",
            capture=True,
        )
        if status == "SUCCESS":
            return
        if status in {"FAILURE", "INTERNAL_ERROR", "TIMEOUT", "CANCELLED", "EXPIRED"}:
            _print_build_diagnostics()
            raise RuntimeError(f"cloud build {build_id} failed with status={status}")
        if time.monotonic() >= deadline:
            run(
                ["gcloud", "builds", "cancel", build_id, f"--project={project_id}"],
                check=False,
            )
            _print_build_diagnostics()
            raise RuntimeError(
                f"cloud build {build_id} exceeded timeout ({timeout_sec}s) and was cancelled"
            )
        time.sleep(poll_sec)
