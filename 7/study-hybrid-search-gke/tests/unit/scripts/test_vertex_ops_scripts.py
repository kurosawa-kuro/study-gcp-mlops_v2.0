from __future__ import annotations

import sys
from urllib.error import URLError

import pytest

from scripts.ops import search
from scripts.ops.vertex import feature_group, pipeline_wait, vector_search
from scripts.setup import backfill_vector_search_index


def test_vector_search_probe_vector_has_expected_shape() -> None:
    probe = vector_search._build_probe_vector()
    assert len(probe) == 768
    assert probe[0] == 1.0
    assert probe[1] == 0.5


def test_ops_search_retries_transient_timeout(monkeypatch, capsys) -> None:
    monkeypatch.setenv("SEARCH_RETRIES", "3")
    monkeypatch.setenv("SEARCH_RETRY_SLEEP", "0")

    attempts = {"count": 0}

    def _fake_once(*, payload: dict[str, object]) -> tuple[int, str]:
        attempts["count"] += 1
        assert payload["query"] == "赤羽駅徒歩10分 ペット可"
        if attempts["count"] == 1:
            raise TimeoutError("timed out")
        return 200, '{"results":[]}'

    monkeypatch.setattr(search, "_search_once", _fake_once)

    assert search.main() == 0
    out = capsys.readouterr().out
    assert "transient failure attempt=1/3" in out
    assert attempts["count"] == 2


def test_ops_search_fails_after_retry_budget(monkeypatch, capsys) -> None:
    monkeypatch.setenv("SEARCH_RETRIES", "2")
    monkeypatch.setenv("SEARCH_RETRY_SLEEP", "0")
    monkeypatch.setattr(search, "_search_once", lambda **_: (_ for _ in ()).throw(URLError("boom")))

    assert search.main() == 1
    captured = capsys.readouterr()
    assert "search timed out after 2 attempt(s)" in captured.err


def test_backfill_build_spec_reads_required_env(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv(
        "VERTEX_VECTOR_SEARCH_INDEX_RESOURCE_NAME",
        "projects/mlops-test/locations/asia-northeast1/indexes/123",
    )
    monkeypatch.setenv("VERTEX_VECTOR_SEARCH_UPSERT_BATCH_SIZE", "123")

    spec = backfill_vector_search_index.build_spec()

    assert spec.project_id == "mlops-test"
    assert spec.location == "asia-northeast1"
    assert spec.index_resource_name.endswith("/indexes/123")
    assert spec.embeddings_table == "mlops-test.feature_mart.property_embeddings"
    assert spec.batch_size == 123


def test_backfill_build_spec_falls_back_to_terraform_output(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.delenv("VERTEX_VECTOR_SEARCH_INDEX_RESOURCE_NAME", raising=False)
    monkeypatch.setattr(
        backfill_vector_search_index,
        "_terraform_output_map",
        lambda: {
            "vector_search_index_resource_name": (
                "projects/mlops-test/locations/asia-northeast1/indexes/123"
            )
        },
    )

    spec = backfill_vector_search_index.build_spec()

    assert spec.index_resource_name.endswith("/indexes/123")


def test_backfill_build_spec_rejects_non_int_batch_size(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setenv(
        "VERTEX_VECTOR_SEARCH_INDEX_RESOURCE_NAME",
        "projects/mlops-test/locations/asia-northeast1/indexes/123",
    )
    monkeypatch.setenv("VERTEX_VECTOR_SEARCH_UPSERT_BATCH_SIZE", "abc")

    try:
        backfill_vector_search_index.build_spec()
    except ValueError as exc:
        assert "must be int" in str(exc)
    else:
        raise AssertionError("expected ValueError for non-int batch size")


def test_feature_group_uses_feature_view_env(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("VERTEX_FEATURE_ONLINE_STORE_ID", "store-a")
    monkeypatch.setenv("VERTEX_FEATURE_VIEW_ID", "view-a")
    monkeypatch.setenv("PROPERTY_ID", "p001")

    calls: list[object] = []

    class _AdminClient:
        def __init__(self, *, client_options):
            calls.append(("admin_init", client_options))

        def get_feature_online_store(self, *, name):
            calls.append(("get_store", name))
            return type(
                "Store",
                (),
                {
                    "name": "projects/123456789/locations/asia-northeast1/featureOnlineStores/store-a",
                    "dedicated_serving_endpoint": type(
                        "Endpoint", (), {"public_endpoint_domain_name": "featurestore.example"}
                    )(),
                },
            )()

        def get_feature_view(self, *, name):
            calls.append(("get_view", name))
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
            return type(
                "Response",
                (),
                {"key_values": type("KeyValues", (), {"features": [object()]})()},
            )()

    import sys
    from types import SimpleNamespace

    fake_module = SimpleNamespace(
        FeatureOnlineStoreAdminServiceClient=_AdminClient,
        FeatureOnlineStoreServiceClient=_ServingClient,
        FeatureViewDataKey=_DataKey,
        FetchFeatureValuesRequest=_Request,
    )
    monkeypatch.setitem(sys.modules, "google.cloud.aiplatform_v1beta1", fake_module)

    assert feature_group.main() == 0
    assert (
        "get_store",
        "projects/mlops-test/locations/asia-northeast1/featureOnlineStores/store-a",
    ) in calls
    assert (
        "get_view",
        "projects/123456789/locations/asia-northeast1/featureOnlineStores/store-a/featureViews/view-a",
    ) in calls
    assert (
        "fetch",
        "projects/123456789/locations/asia-northeast1/featureOnlineStores/store-a/featureViews/view-a",
        "p001",
    ) in calls


def test_feature_group_404_emits_sync_and_bq_diagnostics(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("VERTEX_FEATURE_ONLINE_STORE_ID", "store-a")
    monkeypatch.setenv("VERTEX_FEATURE_VIEW_ID", "view-a")
    monkeypatch.setenv("PROPERTY_ID", "p404")

    class _NotFoundError(Exception):
        code = 404

    class _AdminClient:
        def __init__(self, *, client_options):
            pass

        def get_feature_online_store(self, *, name):
            return type(
                "Store",
                (),
                {
                    "name": "projects/123456789/locations/asia-northeast1/featureOnlineStores/store-a",
                    "dedicated_serving_endpoint": type(
                        "Endpoint", (), {"public_endpoint_domain_name": "featurestore.example"}
                    )(),
                },
            )()

        def get_feature_view(self, *, name):
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
            pass

        def fetch_feature_values(self, *, request):
            raise _NotFoundError("404 entity missing")

    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    fake_module = SimpleNamespace(
        FeatureOnlineStoreAdminServiceClient=_AdminClient,
        FeatureOnlineStoreServiceClient=_ServingClient,
        FeatureViewDataKey=_DataKey,
        FetchFeatureValuesRequest=_Request,
    )
    monkeypatch.setitem(sys.modules, "google.cloud.aiplatform_v1beta1", fake_module)

    fake_bq_module = SimpleNamespace(bigquery=SimpleNamespace())
    fake_client = MagicMock()
    fake_client.query.return_value.result.return_value = [SimpleNamespace(c=5)]
    fake_bq_module.bigquery.Client = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_bq_module)

    with (
        patch.object(feature_group, "_access_token", return_value="tok"),
        patch.object(
            feature_group,
            "_request_json",
            return_value={
                "featureViewSyncs": [
                    {
                        "name": "sync-1",
                        "runTime": {
                            "startTime": "2026-05-02T00:00:00Z",
                            "endTime": "2026-05-02T00:01:00Z",
                        },
                        "finalStatus": {"code": 0},
                    }
                ]
            },
        ),
    ):
        assert feature_group.main() == 1

    captured = capsys.readouterr()
    assert "vertex-feature-group diagnostics:" in captured.out
    assert "recent_sync: name=sync-1" in captured.out
    assert "source_table_rows: table=mlops-test.feature_mart.property_features_daily count=5" in (
        captured.out
    )
    assert "fetch failed: 404 entity missing" in captured.err


def test_vector_search_resolves_ids_from_terraform_outputs(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.delenv("VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT_ID", raising=False)
    monkeypatch.delenv("VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID", raising=False)

    calls: list[tuple[str, object]] = []

    class _Endpoint:
        def __init__(self, *, index_endpoint_name):
            calls.append(("endpoint_init", index_endpoint_name))

        def find_neighbors(self, *, deployed_index_id, queries, num_neighbors):
            calls.append(("find_neighbors", deployed_index_id))
            return [[type("Neighbor", (), {"id": "p001", "distance": 0.1})()]]

    class _AiPlatform:
        MatchingEngineIndexEndpoint = _Endpoint

        @staticmethod
        def init(*, project, location):
            calls.append(("init", (project, location)))

    import sys
    from unittest.mock import patch

    monkeypatch.setitem(sys.modules, "google.cloud.aiplatform", _AiPlatform)

    with patch.object(
        vector_search,
        "_terraform_output_map",
        return_value={
            "vector_search_index_endpoint_id": "4579342784384729088",
            "vector_search_deployed_index_id": "property_embeddings_v3",
        },
    ):
        assert vector_search.main() == 0

    assert ("init", ("mlops-test", "asia-northeast1")) in calls
    assert ("endpoint_init", "4579342784384729088") in calls
    assert ("find_neighbors", "property_embeddings_v3") in calls


def _clear_aiplatform_sys_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    for key in list(sys.modules.keys()):
        if key == "google.cloud.aiplatform" or key.startswith("google.cloud.aiplatform."):
            monkeypatch.delitem(sys.modules, key, raising=False)


def test_pipeline_wait_passes_when_latest_run_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_aiplatform_sys_modules(monkeypatch)
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("PIPELINE_WAIT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("PIPELINE_WAIT_POLL_SECONDS", "0")

    init_calls: list[tuple[str, str]] = []

    import types
    from unittest.mock import MagicMock, patch

    fake_ai = types.ModuleType("google.cloud.aiplatform")
    fake_ai.init = lambda **kw: init_calls.append((kw["project"], kw["location"]))
    fake_ai.PipelineJob = MagicMock()
    monkeypatch.setitem(sys.modules, "google.cloud.aiplatform", fake_ai)

    class _State:
        def __init__(self, value: int):
            self.value = value

    round_n = {"n": 0}

    def fake_latest(*, aiplatform: object, display_name: str):
        round_n["n"] += 1
        st = _State(3) if round_n["n"] == 1 else _State(4)
        return type(
            "Job",
            (),
            {
                "display_name": display_name,
                "state": st,
                "resource_name": "projects/x/locations/r/pipelineJobs/run-1",
            },
        )()

    monkeypatch.setattr(pipeline_wait, "_latest_job", fake_latest)

    with patch.object(pipeline_wait.time, "sleep", return_value=None):
        assert pipeline_wait.main() == 0

    assert ("mlops-test", "asia-northeast1") in init_calls


def test_pipeline_wait_resolves_project_from_gcp_project(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_aiplatform_sys_modules(monkeypatch)
    monkeypatch.delenv("PROJECT_ID", raising=False)
    monkeypatch.setenv("GCP_PROJECT", "mlops-from-gcp-env")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("PIPELINE_WAIT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("PIPELINE_WAIT_POLL_SECONDS", "0")

    init_calls: list[tuple[str, str]] = []

    import types
    from unittest.mock import MagicMock, patch

    fake_ai = types.ModuleType("google.cloud.aiplatform")
    fake_ai.init = lambda **kw: init_calls.append((kw["project"], kw["location"]))
    fake_ai.PipelineJob = MagicMock()
    monkeypatch.setitem(sys.modules, "google.cloud.aiplatform", fake_ai)

    class _State:
        def __init__(self, value: int):
            self.value = value

    def fake_latest(*, aiplatform: object, display_name: str):
        return type(
            "Job",
            (),
            {
                "display_name": display_name,
                "state": _State(4),
                "resource_name": "projects/x/locations/r/pipelineJobs/run-gcp",
            },
        )()

    monkeypatch.setattr(pipeline_wait, "_latest_job", fake_latest)

    with patch.object(pipeline_wait.time, "sleep", return_value=None):
        assert pipeline_wait.main() == 0

    assert ("mlops-from-gcp-env", "asia-northeast1") in init_calls


def test_pipeline_wait_fails_when_latest_run_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_aiplatform_sys_modules(monkeypatch)
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    monkeypatch.setenv("VERTEX_LOCATION", "asia-northeast1")
    monkeypatch.setenv("PIPELINE_WAIT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("PIPELINE_WAIT_POLL_SECONDS", "0")

    import types
    from unittest.mock import MagicMock

    fake_ai = types.ModuleType("google.cloud.aiplatform")
    fake_ai.init = lambda **kw: None
    fake_ai.PipelineJob = MagicMock()
    monkeypatch.setitem(sys.modules, "google.cloud.aiplatform", fake_ai)

    class _State:
        def __init__(self, value: int):
            self.value = value

    def fake_latest(*, aiplatform: object, display_name: str):
        return type(
            "Job",
            (),
            {
                "display_name": display_name,
                "state": _State(5),
                "resource_name": "projects/x/locations/r/pipelineJobs/run-1",
            },
        )()

    monkeypatch.setattr(pipeline_wait, "_latest_job", fake_latest)

    assert pipeline_wait.main() == 1
