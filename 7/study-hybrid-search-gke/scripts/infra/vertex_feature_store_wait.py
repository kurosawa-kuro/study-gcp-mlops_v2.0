"""Block until Vertex Feature Group / Feature Online Store names are GC'd.

After ``destroy-all``, Vertex AI keeps ``featureGroups/<id>`` and
``featureOnlineStores/<id>`` in a **deleting** state for minutes. A naïve
immediate ``deploy-all`` runs ``terraform apply`` and hits::

    Error 409: Re-using the same name as a FeatureGroup being deleted

This module polls the regional Vertex REST **list** APIs (same host as
``scripts/infra/state_recovery._recover_feature_store``) until the canonical
IDs are absent, so creates become safe.

Duplication note: list URL shape matches ``state_recovery._aiplatform_get`` —
keep IDs in sync with ``FEATURE_GROUPS`` / ``FEATURE_ONLINE_STORES`` there.
"""

from __future__ import annotations

import json
import subprocess
import time

from scripts._common import env


def _access_token() -> str | None:
    proc = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def _rest_get(token: str, url: str) -> dict:
    proc = subprocess.run(
        ["curl", "-sS", "-H", f"Authorization: Bearer {token}", url],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout) if (proc.stdout or "").strip() else {}
    except json.JSONDecodeError:
        return {}


def _feature_group_ids(project_id: str, region: str, token: str) -> set[str]:
    base = (
        f"https://{region}-aiplatform.googleapis.com/v1beta1/"
        f"projects/{project_id}/locations/{region}"
    )
    payload = _rest_get(token, f"{base}/featureGroups")
    return {
        r.get("name", "").rsplit("/", 1)[-1]
        for r in (payload.get("featureGroups") or [])
        if r.get("name")
    }


def _feature_online_store_ids(project_id: str, region: str, token: str) -> set[str]:
    base = (
        f"https://{region}-aiplatform.googleapis.com/v1beta1/"
        f"projects/{project_id}/locations/{region}"
    )
    payload = _rest_get(token, f"{base}/featureOnlineStores")
    return {
        r.get("name", "").rsplit("/", 1)[-1]
        for r in (payload.get("featureOnlineStores") or [])
        if r.get("name")
    }


def wait_until_feature_store_names_released(
    project_id: str,
    region: str,
    *,
    feature_group_id: str = "property_features",
    feature_online_store_id: str = "mlops_dev_feature_store",
    timeout_seconds: int = 3600,
    poll_seconds: int = 30,
) -> None:
    """Poll until neither ID appears in list APIs (safe for terraform create)."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        token = _access_token()
        if not token:
            print(
                "[vertex_feature_store_wait] no gcloud access token — "
                "skip Feature Store wait (non-GCP / CI)"
            )
            return

        fg = _feature_group_ids(project_id, region, token)
        fos = _feature_online_store_ids(project_id, region, token)
        pending_fg = feature_group_id in fg
        pending_fos = feature_online_store_id in fos
        if not pending_fg and not pending_fos:
            print(
                "==> Vertex Feature Store names released "
                f"(featureGroup={feature_group_id!r}, "
                f"featureOnlineStore={feature_online_store_id!r}) — proceed"
            )
            return

        print(
            "==> waiting for async Vertex Feature Store delete "
            f"(featureGroup present={pending_fg}, featureOnlineStore present={pending_fos})"
        )
        time.sleep(poll_seconds)

    raise RuntimeError(
        f"Vertex Feature Group {feature_group_id!r} / Feature Online Store "
        f"{feature_online_store_id!r} still listed after {timeout_seconds}s — "
        "GCP eventual consistency cap hit"
    )


def wait_until_feature_store_names_released_from_env(
    *,
    timeout_seconds: int = 3600,
    poll_seconds: int = 30,
) -> None:
    """Convenience: ``PROJECT_ID`` + ``VERTEX_LOCATION`` or ``REGION``."""
    pid = env("PROJECT_ID")
    rgn = env("VERTEX_LOCATION") or env("REGION") or "asia-northeast1"
    wait_until_feature_store_names_released(
        pid,
        rgn,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )
