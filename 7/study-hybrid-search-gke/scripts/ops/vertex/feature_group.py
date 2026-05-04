"""Fetch a single property's online featureValues from the Vertex Feature
Online Store.

Phase 7 (Run 2) added the Optimized FeatureOnlineStore via
``infra/terraform/modules/vertex/main.tf``. After ``terraform apply`` +
the first sync completes, the store auto-provisions a regional public
endpoint (``dedicatedServingEndpoint.publicEndpointDomainName``) of the
shape ``<NUMERIC>.<region>-<project_number>.featurestore.vertexai.goog``.
The Optimized type **only accepts requests on that endpoint**, not on
the global ``aiplatform.googleapis.com`` host — clients constructed
with the default endpoint fail with ``501 Operation is not implemented``.

This script:
1. Reads the FeatureOnlineStore resource to discover the public
   endpoint domain (so callers don't have to hardcode it).
2. Constructs ``FeatureOnlineStoreServiceClient`` against that endpoint.
3. Issues ``FetchFeatureValues`` for ``PROPERTY_ID``.

Usage::

    PROPERTY_ID=p001 make ops-vertex-feature-group

Exit codes:
    0  — entity returned at least one feature value
    1  — config error / endpoint not yet provisioned / IAM / not-found
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from typing import Any

from scripts._common import env, fail, run


def _access_token() -> str:
    proc = run(["gcloud", "auth", "print-access-token"], capture=True, check=False)
    token = (proc.stdout or "").strip()
    if proc.returncode != 0 or not token:
        raise RuntimeError("gcloud auth print-access-token failed")
    return token


def _request_json(url: str, *, token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        import json

        return json.loads(resp.read().decode("utf-8") or "{}")


def _emit_404_diagnostics(*, project_id: str, region: str, feature_view: str) -> None:
    print("vertex-feature-group diagnostics:")
    try:
        token = _access_token()
        url = (
            f"https://{region}-aiplatform.googleapis.com/v1beta1/"
            f"{urllib.parse.quote(feature_view, safe='/')}/featureViewSyncs?pageSize=3"
        )
        payload = _request_json(url, token=token)
        syncs = payload.get("featureViewSyncs", []) or []
        if not syncs:
            print("  recent_syncs: none")
        for sync in syncs[:3]:
            runtime = sync.get("runTime") or {}
            final_status = sync.get("finalStatus") or {}
            print(
                "  recent_sync:"
                f" name={sync.get('name', '-')}"
                f" start={runtime.get('startTime', '-')}"
                f" end={runtime.get('endTime', '-')}"
                f" final_code={final_status.get('code', '-')}"
            )
    except Exception as exc:
        print(f"  recent_syncs_lookup_failed: {exc}")

    table = f"{project_id}.feature_mart.property_features_daily"
    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=project_id)
        rows = list(client.query(f"SELECT COUNT(*) AS c FROM `{table}`").result())
        count = int(rows[0].c if rows else 0)
        print(f"  source_table_rows: table={table} count={count}")
    except Exception as exc:
        print(f"  source_table_count_failed: table={table} error={exc}")

    print(
        "  next_action: run FeatureView sync again, wait for final_code=0, "
        "and confirm seed rows exist in property_features_daily."
    )


def _canonical_feature_view_name(
    *,
    admin: Any,
    store_name: str,
    feature_view_id: str,
) -> str:
    raw_name = f"{store_name}/featureViews/{feature_view_id}"
    try:
        view = admin.get_feature_view(name=raw_name)
    except Exception:
        return raw_name
    return str(getattr(view, "name", "") or raw_name)


def main() -> int:
    project_id = env("PROJECT_ID")
    region = env("VERTEX_LOCATION", env("REGION", "asia-northeast1"))
    online_store_id = env("VERTEX_FEATURE_ONLINE_STORE_ID", "mlops_dev_feature_store")
    feature_view_id = env("VERTEX_FEATURE_VIEW_ID", "property_features")
    property_id = os.environ.get("PROPERTY_ID", "p001")
    if not project_id:
        return fail("vertex-feature-group: PROJECT_ID is required")

    try:
        from google.cloud.aiplatform_v1beta1 import (
            FeatureOnlineStoreAdminServiceClient,
            FeatureOnlineStoreServiceClient,
            FeatureViewDataKey,
            FetchFeatureValuesRequest,
        )
    except ImportError:
        return fail("vertex-feature-group: google-cloud-aiplatform[v1beta1] required.")

    # 1. Discover the regional public endpoint via the Admin API.
    admin_endpoint = f"{region}-aiplatform.googleapis.com"
    admin = FeatureOnlineStoreAdminServiceClient(client_options={"api_endpoint": admin_endpoint})
    store_name = f"projects/{project_id}/locations/{region}/featureOnlineStores/{online_store_id}"
    try:
        store = admin.get_feature_online_store(name=store_name)
    except Exception as exc:
        return fail(f"vertex-feature-group: admin lookup failed: {exc}")

    endpoint = getattr(store, "dedicated_serving_endpoint", None)
    public_domain = (
        getattr(endpoint, "public_endpoint_domain_name", "") if endpoint is not None else ""
    )
    if not public_domain:
        return fail(
            "vertex-feature-group: dedicatedServingEndpoint.publicEndpointDomainName "
            "is empty — Optimized FeatureOnlineStore not yet provisioned. Wait 20-30 min "
            "after terraform apply + initial sync, then retry."
        )

    print(f"vertex-feature-group: public endpoint = {public_domain}")

    # 2. Construct the data-plane client against the regional public endpoint.
    serving = FeatureOnlineStoreServiceClient(client_options={"api_endpoint": public_domain})
    store_resource_name = str(getattr(store, "name", "") or store_name)
    feature_view = _canonical_feature_view_name(
        admin=admin,
        store_name=store_resource_name,
        feature_view_id=feature_view_id,
    )
    req = FetchFeatureValuesRequest(
        feature_view=feature_view,
        data_key=FeatureViewDataKey(key=property_id),
    )
    try:
        resp = serving.fetch_feature_values(request=req)
    except Exception as exc:
        code = getattr(exc, "code", None)
        text = str(exc)
        if code == 404 or "404" in text:
            _emit_404_diagnostics(project_id=project_id, region=region, feature_view=feature_view)
        return fail(f"vertex-feature-group: fetch failed: {exc}")

    kv = list(getattr(resp.key_values, "features", []) or [])
    if not kv:
        return fail(
            f"vertex-feature-group: empty feature set for property_id={property_id!r}. "
            f"Check that the FeatureView sync ran (cron `0 * * * *`) and the entity exists."
        )

    print(f"vertex-feature-group PASS: {len(kv)} feature(s) for property_id={property_id!r}")
    for fv in kv[:20]:
        print(f"  {getattr(fv, 'name', '-')} = {getattr(fv, 'value', '-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
