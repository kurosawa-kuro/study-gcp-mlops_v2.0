"""``FeatureFetcher`` adapter — Vertex AI Feature Online Store (Phase 7 PR-2).

Phase 5+ production path. Calls
``FeatureOnlineStoreServiceClient.fetch_feature_values`` against the
deployed FeatureView. Source-of-truth for the underlying data is
BigQuery ``feature_mart.property_features_daily``; FOS sync (hourly cron
configured in ``infra/terraform/modules/vertex/main.tf``) keeps the
serving-side index fresh.

Mirrors the pattern in ``scripts/ops/vertex/feature_group.py`` —
discovers the regional public endpoint via the Admin API and constructs
the data-plane client against it. ``client_factory`` injection keeps
unit tests free of ``google.cloud.aiplatform_v1beta1`` imports
(roadmap §3.2 ローカル完結 受け入れ条件).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.protocols.feature_fetcher import FeatureRow

ClientFactory = Callable[[str], Any]
"""``client_factory(public_endpoint_domain) -> data-plane client``."""

EndpointResolver = Callable[[], str]
"""``endpoint_resolver() -> public_endpoint_domain``."""


class FeatureOnlineStoreFetcher:
    """Phase 5+ production — Vertex AI Feature Online Store.

    Args:
        feature_view: Fully-qualified ``FeatureView`` resource name, e.g.
            ``projects/{p}/locations/{r}/featureOnlineStores/{store}/featureViews/{view}``.
        endpoint_resolver: callable that returns the regional public
            endpoint domain (looked up once via Admin API + cached). Tests
            inject a constant lambda; production composition root passes
            a callable that runs the Admin lookup lazily.
        client_factory: callable that builds the data-plane
            ``FeatureOnlineStoreServiceClient`` against the public
            endpoint. Tests inject a mock; production leaves this
            ``None`` so the adapter lazy-imports the real SDK.
    """

    def __init__(
        self,
        *,
        feature_view: str,
        endpoint_resolver: EndpointResolver,
        client_factory: ClientFactory | None = None,
    ) -> None:
        if not feature_view:
            raise ValueError("feature_view is required")
        self._feature_view = feature_view
        self._endpoint_resolver = endpoint_resolver
        self._client_factory = client_factory
        self._client: Any | None = None
        self._fetch_request_factory: Any | None = None
        self._data_key_factory: Any | None = None
        self._canonical_feature_view: str | None = None

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        endpoint = self._endpoint_resolver()
        if not endpoint:
            raise RuntimeError(
                "FeatureOnlineStore public endpoint is empty — Optimized "
                "Online Store may not yet be provisioned. Wait for the initial "
                "sync (cron `0 * * * *`) and retry."
            )
        if self._client_factory is not None:
            self._client = self._client_factory(endpoint)
        else:
            from google.cloud.aiplatform_v1beta1 import (  # lazy
                FeatureOnlineStoreAdminServiceClient,
                FeatureOnlineStoreServiceClient,
                FeatureViewDataKey,
                FetchFeatureValuesRequest,
            )

            self._client = FeatureOnlineStoreServiceClient(
                client_options={"api_endpoint": endpoint}
            )
            self._fetch_request_factory = FetchFeatureValuesRequest
            self._data_key_factory = FeatureViewDataKey
            self._canonical_feature_view = self._resolve_canonical_feature_view(
                FeatureOnlineStoreAdminServiceClient
            )
        return self._client

    def _resolve_canonical_feature_view(self, admin_client_cls: Any) -> str:
        location = _resource_part(self._feature_view, "locations")
        if not location:
            return self._feature_view
        try:
            admin = admin_client_cls(
                client_options={"api_endpoint": f"{location}-aiplatform.googleapis.com"}
            )
            view = admin.get_feature_view(name=self._feature_view)
        except Exception:
            return self._feature_view
        return str(getattr(view, "name", "") or self._feature_view)

    def fetch(self, property_ids: list[str]) -> dict[str, FeatureRow]:
        if not property_ids:
            return {}
        client = self._resolve_client()
        out: dict[str, FeatureRow] = {}
        for pid in property_ids:
            request = self._build_request(pid)
            try:
                response = client.fetch_feature_values(request=request)
            except Exception:
                # Treat per-id failures as missing data so /search keeps
                # serving with degraded features (None → LightGBM defaults).
                out[pid] = FeatureRow(property_id=pid, ctr=None, fav_rate=None, inquiry_rate=None)
                continue
            out[pid] = _row_from_response(pid, response)
        return out

    def _build_request(self, property_id: str) -> Any:
        # When ``client_factory`` was injected (tests), we did not import the
        # SDK request types. Fall back to a duck-typed dict the test client
        # can introspect; production pulled the proper proto types in
        # ``_resolve_client``.
        if self._fetch_request_factory is None or self._data_key_factory is None:
            return {
                "feature_view": self._canonical_feature_view or self._feature_view,
                "data_key": {"key": property_id},
            }
        return self._fetch_request_factory(
            feature_view=self._canonical_feature_view or self._feature_view,
            data_key=self._data_key_factory(key=property_id),
        )


def _resource_part(resource_name: str, key: str) -> str:
    parts = resource_name.split("/")
    try:
        index = parts.index(key)
    except ValueError:
        return ""
    if index + 1 >= len(parts):
        return ""
    return parts[index + 1]


def _row_from_response(property_id: str, response: Any) -> FeatureRow:
    """Convert a ``FetchFeatureValuesResponse`` to a ``FeatureRow``.

    The response carries a ``key_values.features`` repeated field of
    ``FeatureValueList`` entries, each with ``name`` (str) +
    ``value.{double_value,int64_value,string_value,...}``. We extract by
    name and coerce to ``float | None``.
    """
    features = _safe_features(response)
    extracted: dict[str, float | None] = {"ctr": None, "fav_rate": None, "inquiry_rate": None}
    for fv in features:
        name = str(getattr(fv, "name", ""))
        if name not in extracted:
            continue
        extracted[name] = _coerce_float(getattr(fv, "value", None))
    return FeatureRow(
        property_id=property_id,
        ctr=extracted["ctr"],
        fav_rate=extracted["fav_rate"],
        inquiry_rate=extracted["inquiry_rate"],
    )


def _safe_features(response: Any) -> list[Any]:
    key_values = getattr(response, "key_values", None)
    if key_values is None:
        return []
    return list(getattr(key_values, "features", []) or [])


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    for attr in ("double_value", "float_value", "int64_value"):
        raw = getattr(value, attr, None)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
    return None
