"""POST /jobs/check-retrain on search-api with an OIDC token. The endpoint
inspects training_runs / feedback freshness and returns whether the
retrain-trigger Pub/Sub topic should fire (used by Cloud Scheduler daily).
"""

from __future__ import annotations

import os
import sys

from scripts._common import fail, print_pretty, resolve_api_target


def _diag(msg: str) -> None:
    """V5 fix (2026-05-03 §4.1): Composer Pod log に必ず流れる stderr 診断。"""
    print(f"[check_retrain DIAG] {msg}", file=sys.stderr, flush=True)


def main() -> int:
    # Composer Pod 上で実行された際に env / target 解決を必ず可視化する。
    # Pod stdout/stderr が Composer log に流れるので、何が起きているか追える
    # ようにする (Run 1/2 で Pod exit_code=1 のみで原因不明だった反省)。
    for key in ("API_URL", "API_EXTERNAL_URL", "API_HOST_HEADER", "API_INSECURE_TLS", "TARGET"):
        _diag(f"env {key}={os.environ.get(key, '<unset>')!r}")

    try:
        target = resolve_api_target()
    except Exception as exc:
        _diag(f"resolve_api_target FAILED: {exc!r}")
        return fail(f"check-retrain config error: {exc}")
    _diag(
        f"resolved target mode={target.mode} url={target.url!r} "
        f"host_header={target.host_header!r} verify_tls={target.verify_tls} "
        f"has_token={bool(target.token)}"
    )

    _diag("calling POST /jobs/check-retrain ...")
    try:
        status, body = target.call("POST", "/jobs/check-retrain")
    except Exception as exc:
        _diag(f"target.call FAILED: {type(exc).__name__}: {exc!r}")
        return fail(f"check-retrain transport error: {type(exc).__name__}: {exc}")
    _diag(f"response status={status} body_len={len(body)} body={body[:500]!r}")
    if status != 200:
        return fail(f"check-retrain returned HTTP {status}: {body}")
    print_pretty(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
