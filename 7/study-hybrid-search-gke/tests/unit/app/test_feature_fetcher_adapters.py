"""Unit tests for the canonical Feature Online Store adapter (Phase 7 W2-8 後).

W2-8 で BigQueryFeatureFetcher は撤去。本 phase の唯一の FeatureFetcher 実装は
``FeatureOnlineStoreFetcher`` (Vertex AI Feature View 経由)。SDK 呼び出しは
``client_factory`` 注入 seam で stub し、``google.cloud.aiplatform_v1beta1``
は import せずに covers する。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.adapters.feature_online_store_fetcher import FeatureOnlineStoreFetcher
from app.services.protocols.feature_fetcher import FeatureRow

# ----------------------------------------------------------------------------
# FeatureOnlineStoreFetcher
# ----------------------------------------------------------------------------


def _make_feature_value(double: float | None = None, int64: int | None = None) -> Any:
    val = MagicMock()
    val.double_value = double if double is not None else None
    val.float_value = None
    val.int64_value = int64 if int64 is not None else None
    return val


def _make_feature(name: str, value: Any) -> Any:
    fv = MagicMock()
    fv.name = name
    fv.value = value
    return fv


def _fos_client_returning(features_per_pid: dict[str, list[Any]]) -> Any:
    """Stub a FOS client; ``fetch_feature_values`` returns features per id."""
    client = MagicMock()

    def _fetch(*, request: Any) -> Any:
        # `request` is the duck-typed dict the adapter builds when no
        # SDK is present (see FeatureOnlineStoreFetcher._build_request).
        pid = request["data_key"]["key"]
        response = MagicMock()
        response.key_values.features = features_per_pid.get(pid, [])
        return response

    client.fetch_feature_values.side_effect = _fetch
    return client


def test_fos_fetcher_extracts_three_known_features() -> None:
    client = _fos_client_returning(
        {
            "p001": [
                _make_feature("ctr", _make_feature_value(double=0.12)),
                _make_feature("fav_rate", _make_feature_value(double=0.05)),
                _make_feature("inquiry_rate", _make_feature_value(double=0.02)),
            ]
        }
    )
    fetcher = FeatureOnlineStoreFetcher(
        feature_view="projects/x/locations/r/featureOnlineStores/s/featureViews/v",
        endpoint_resolver=lambda: "r-aiplatform.googleapis.com",
        client_factory=lambda _ep: client,
    )

    out = fetcher.fetch(["p001"])

    assert out["p001"] == FeatureRow(
        property_id="p001",
        ctr=pytest.approx(0.12),
        fav_rate=pytest.approx(0.05),
        inquiry_rate=pytest.approx(0.02),
    )


def test_fos_fetcher_ignores_unknown_feature_names() -> None:
    """Extra features in the FOS view (e.g. display fields) are dropped."""
    client = _fos_client_returning(
        {
            "p001": [
                _make_feature("ctr", _make_feature_value(double=0.12)),
                _make_feature("rent", _make_feature_value(int64=80_000)),
            ]
        }
    )
    fetcher = FeatureOnlineStoreFetcher(
        feature_view="projects/x/locations/r/featureOnlineStores/s/featureViews/v",
        endpoint_resolver=lambda: "r-aiplatform.googleapis.com",
        client_factory=lambda _ep: client,
    )

    out = fetcher.fetch(["p001"])

    assert out["p001"].ctr == pytest.approx(0.12)
    assert out["p001"].fav_rate is None
    assert out["p001"].inquiry_rate is None


def test_fos_fetcher_returns_all_none_when_per_id_call_raises() -> None:
    """A single failing fetch must not poison the whole batch."""
    client = MagicMock()

    def _fetch(*, request: Any) -> Any:
        pid = request["data_key"]["key"]
        if pid == "p_bad":
            raise RuntimeError("simulated FOS 503")
        response = MagicMock()
        response.key_values.features = [
            _make_feature("ctr", _make_feature_value(double=0.5)),
        ]
        return response

    client.fetch_feature_values.side_effect = _fetch
    fetcher = FeatureOnlineStoreFetcher(
        feature_view="projects/x/locations/r/featureOnlineStores/s/featureViews/v",
        endpoint_resolver=lambda: "r-aiplatform.googleapis.com",
        client_factory=lambda _ep: client,
    )

    out = fetcher.fetch(["p_good", "p_bad"])
    assert out["p_good"].ctr == pytest.approx(0.5)
    assert out["p_bad"] == FeatureRow(
        property_id="p_bad", ctr=None, fav_rate=None, inquiry_rate=None
    )


def test_fos_fetcher_returns_empty_for_empty_input() -> None:
    client = MagicMock()
    fetcher = FeatureOnlineStoreFetcher(
        feature_view="projects/x/locations/r/featureOnlineStores/s/featureViews/v",
        endpoint_resolver=lambda: "r-aiplatform.googleapis.com",
        client_factory=lambda _ep: client,
    )
    assert fetcher.fetch([]) == {}
    client.fetch_feature_values.assert_not_called()


def test_fos_fetcher_raises_when_endpoint_resolver_returns_empty() -> None:
    fetcher = FeatureOnlineStoreFetcher(
        feature_view="projects/x/locations/r/featureOnlineStores/s/featureViews/v",
        endpoint_resolver=lambda: "",
        client_factory=lambda _ep: MagicMock(),
    )
    with pytest.raises(RuntimeError, match="public endpoint is empty"):
        fetcher.fetch(["p001"])


def test_fos_fetcher_rejects_empty_feature_view() -> None:
    with pytest.raises(ValueError, match="feature_view"):
        FeatureOnlineStoreFetcher(
            feature_view="",
            endpoint_resolver=lambda: "endpoint",
        )


def test_fos_fetcher_canonicalizes_feature_view_name_via_admin_lookup(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class _AdminClient:
        def __init__(self, *, client_options):
            calls.append(("admin_init", client_options))

        def get_feature_view(self, *, name):
            calls.append(("get_feature_view", name))
            return type(
                "FeatureView",
                (),
                {
                    "name": "projects/123456789/locations/asia-northeast1/featureOnlineStores/store-a/featureViews/view-a"
                },
            )()

    class _DataKey:
        def __init__(self, *, key):
            self.key = key

    class _Request:
        def __init__(self, *, feature_view, data_key):
            self.feature_view = feature_view
            self.data_key = data_key

    class _ServingClient:
        def __init__(self, *, client_options):
            calls.append(("serving_init", client_options))

        def fetch_feature_values(self, *, request):
            calls.append(("fetch", request.feature_view, request.data_key.key))
            response = MagicMock()
            response.key_values.features = []
            return response

    import sys
    from types import SimpleNamespace

    fake_module = SimpleNamespace(
        FeatureOnlineStoreAdminServiceClient=_AdminClient,
        FeatureOnlineStoreServiceClient=_ServingClient,
        FeatureViewDataKey=_DataKey,
        FetchFeatureValuesRequest=_Request,
    )
    monkeypatch.setitem(sys.modules, "google.cloud.aiplatform_v1beta1", fake_module)

    fetcher = FeatureOnlineStoreFetcher(
        feature_view=(
            "projects/mlops-test/locations/asia-northeast1/featureOnlineStores/store-a/"
            "featureViews/view-a"
        ),
        endpoint_resolver=lambda: "featurestore.example",
    )

    fetcher.fetch(["p001"])

    assert (
        "get_feature_view",
        "projects/mlops-test/locations/asia-northeast1/featureOnlineStores/store-a/featureViews/view-a",
    ) in calls
    assert (
        "fetch",
        "projects/123456789/locations/asia-northeast1/featureOnlineStores/store-a/featureViews/view-a",
        "p001",
    ) in calls
