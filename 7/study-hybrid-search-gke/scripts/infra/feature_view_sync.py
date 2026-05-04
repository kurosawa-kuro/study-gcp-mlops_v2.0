"""Trigger a manual Vertex Feature View sync and wait for completion.

Phase 7 Wave 2 live verification found that the hourly cron sync often runs
before `seed_minimal.py` populates `feature_mart.property_features_daily`.
That leaves the Feature View empty after `make deploy-all`, so the first
`feature_group.py` probe returns 404 even though Terraform apply succeeded.

This helper closes that gap by:
1. reading the Feature Online Store / Feature View IDs from Terraform outputs,
2. calling the regional `featureViews:sync` REST API after seed-test,
3. polling `featureViewSyncs:list` until the new sync reaches finalStatus=OK.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from scripts._common import env, run

INFRA = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "environments" / "dev"


def _terraform_output_map() -> dict[str, str]:
    proc = run(
        ["terraform", f"-chdir={INFRA}", "output", "-json"],
        capture=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit("[error] terraform output -json failed while resolving Feature View IDs")
    payload = json.loads(proc.stdout or "{}")
    resolved: dict[str, str] = {}
    for key, meta in payload.items():
        value = meta.get("value", "") if isinstance(meta, dict) else ""
        resolved[key] = str(value or "")
    return resolved


def _access_token() -> str:
    proc = run(["gcloud", "auth", "print-access-token"], capture=True, check=False)
    token = (proc.stdout or "").strip()
    if proc.returncode != 0 or not token:
        raise SystemExit("[error] gcloud auth print-access-token failed for Feature View sync")
    return token


def _request_json(
    url: str,
    *,
    method: str = "GET",
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _feature_view_resource(project_id: str, region: str, store_id: str, view_id: str) -> str:
    return (
        f"projects/{project_id}/locations/{region}/featureOnlineStores/"
        f"{store_id}/featureViews/{view_id}"
    )


def _latest_sync_name(feature_view: str, token: str, region: str) -> str:
    payload = _list_syncs(feature_view, token=token, region=region, page_size=1)
    syncs = payload.get("featureViewSyncs", []) or []
    if not syncs:
        return ""
    first = syncs[0]
    return str(first.get("name") or "")


def _list_syncs(
    feature_view: str, *, token: str, region: str, page_size: int = 5
) -> dict[str, Any]:
    parent = urllib.parse.quote(feature_view, safe="/")
    url = (
        f"https://{region}-aiplatform.googleapis.com/v1beta1/"
        f"{parent}/featureViewSyncs?pageSize={page_size}"
    )
    return _request_json(url, token=token)


def trigger_and_wait(
    *,
    project_id: str,
    region: str,
    store_id: str,
    view_id: str,
    timeout_sec: int = 1800,
    poll_sec: int = 15,
) -> None:
    feature_view = _feature_view_resource(project_id, region, store_id, view_id)
    token = _access_token()
    before_name = _latest_sync_name(feature_view, token, region)
    sync_url = (
        f"https://{region}-aiplatform.googleapis.com/v1beta1/"
        f"{urllib.parse.quote(feature_view, safe='/')}:sync"
    )

    print(f"==> trigger FeatureView sync: {feature_view}")
    _request_json(sync_url, method="POST", token=token, payload={})

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        payload = _list_syncs(feature_view, token=token, region=region, page_size=5)
        syncs = payload.get("featureViewSyncs", []) or []
        if syncs:
            latest = syncs[0]
            latest_name = str(latest.get("name") or "")
            latest_code = int((latest.get("finalStatus") or {}).get("code") or 0)
            latest_end = str((latest.get("runTime") or {}).get("endTime") or "")
            if latest_name and latest_name != before_name:
                if latest_code != 0:
                    message = str((latest.get("finalStatus") or {}).get("message") or "")
                    raise SystemExit(
                        "[error] FeatureView sync failed "
                        f"name={latest_name} code={latest_code} message={message}"
                    )
                if latest_end:
                    print(f"==> FeatureView sync complete name={latest_name} end_time={latest_end}")
                    return
        print(f"    waiting for FeatureView sync completion... sleep={poll_sec}s")
        time.sleep(poll_sec)
    raise SystemExit(
        "[error] FeatureView sync polling timed out "
        f"after {timeout_sec}s for feature view {feature_view}"
    )


def main() -> int:
    project_id = env("PROJECT_ID")
    region = env("VERTEX_LOCATION", env("REGION", "asia-northeast1"))
    outputs = _terraform_output_map()
    store_id = env(
        "VERTEX_FEATURE_ONLINE_STORE_ID",
        outputs.get("vertex_feature_online_store_id", ""),
    )
    view_id = env(
        "VERTEX_FEATURE_VIEW_ID",
        outputs.get("vertex_feature_view_id", ""),
    )
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")
    if not store_id or not view_id:
        print("==> FeatureView sync skipped: Feature Online Store outputs are empty")
        return 0
    trigger_and_wait(
        project_id=project_id,
        region=region,
        store_id=store_id,
        view_id=view_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
