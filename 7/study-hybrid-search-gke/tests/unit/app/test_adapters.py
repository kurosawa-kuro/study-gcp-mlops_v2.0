"""Tests for concrete adapters in app.adapters (Phase 6: KServe encoder/reranker)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from app.services.adapters import (
    KServeEncoder,
    KServeReranker,
    PubSubPublisher,
    create_retrain_queries,
)


def _fake_httpx_client(response_json: Any, *, status_code: int = 200) -> MagicMock:
    fake_response = MagicMock()
    fake_response.status_code = status_code
    fake_response.text = ""
    fake_response.json.return_value = response_json
    fake_response.raise_for_status.return_value = None
    client = MagicMock()
    client.post.return_value = fake_response
    return client


def test_create_retrain_queries_wires_bigquery_client() -> None:
    from app.services.adapters import BigQueryRetrainQueries

    fake_bq_client = MagicMock()
    fake_bq_client.query.return_value.result.return_value = iter([{"ts": None}])
    with patch("google.cloud.bigquery.Client", return_value=fake_bq_client) as client_cls:
        queries = create_retrain_queries(
            project_id="p",
            training_runs_table="p.m.training_runs",
        )
        queries.last_run_finished_at()

    client_cls.assert_called_once_with(project="p")
    assert isinstance(queries, BigQueryRetrainQueries)
    fake_bq_client.query.assert_called_once()
    assert "p.m.training_runs" in fake_bq_client.query.call_args.args[0]


def test_pubsub_publisher_publishes_json_bytes() -> None:
    fake_client = MagicMock()
    fake_client.topic_path.return_value = "projects/p/topics/retrain-trigger"
    fake_future = MagicMock()
    fake_client.publish.return_value = fake_future

    with patch("google.cloud.pubsub_v1.PublisherClient", return_value=fake_client):
        publisher = PubSubPublisher(project_id="p", topic="retrain-trigger")
        publisher.publish({"reasons": ["ndcg_drop=0.05>=0.03"], "日本語": "ok"})

    fake_client.topic_path.assert_called_once_with("p", "retrain-trigger")
    fake_client.publish.assert_called_once()
    call_args = fake_client.publish.call_args.args
    assert call_args[0] == "projects/p/topics/retrain-trigger"
    decoded = json.loads(call_args[1].decode("utf-8"))
    assert decoded == {"reasons": ["ndcg_drop=0.05>=0.03"], "日本語": "ok"}
    fake_future.result.assert_called_once()


def test_kserve_encoder_parses_embedding_dict_response_v1() -> None:
    fake_client = _fake_httpx_client({"predictions": [{"embedding": [0.1, 0.2, 0.3]}]})

    adapter = KServeEncoder(
        endpoint_url="http://property-encoder.kserve-inference.svc.cluster.local/v1/models/property-encoder:predict",
        client=fake_client,
        expected_dim=0,  # disable strict 768d check for tiny test vector
    )
    vector = adapter.embed("赤羽駅徒歩10分", "query")

    fake_client.post.assert_called_once()
    sent_json = fake_client.post.call_args.kwargs["json"]
    # Phase 7 Run 2: encoder runtime を HF stock runtime に切替えたため、
    # adapter は client 側で E5 prefix (`query: ` / `passage: `) を付与し、
    # ペイロードは ``{"instances": ["query: ..."]}`` の bare list 形式で送る。
    assert sent_json == {"instances": ["query: 赤羽駅徒歩10分"]}
    assert vector == [0.1, 0.2, 0.3]
    assert "property-encoder" in adapter.endpoint_name


def test_kserve_reranker_parses_scalar_scores_v1() -> None:
    fake_client = _fake_httpx_client({"predictions": [0.9, 0.4, 0.1]})

    adapter = KServeReranker(
        endpoint_url="http://property-reranker.kserve-inference.svc.cluster.local/v1/models/property-reranker:predict",
        client=fake_client,
    )
    scores = adapter.predict([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])

    fake_client.post.assert_called_once()
    sent_json = fake_client.post.call_args.kwargs["json"]
    assert sent_json == {"instances": [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]}
    assert scores == [0.9, 0.4, 0.1]
    assert "property-reranker" in adapter.model_path


def test_kserve_encoder_parses_v2_open_inference_response() -> None:
    fake_client = _fake_httpx_client({"outputs": [{"name": "embedding", "data": [[0.1, 0.2]]}]})

    adapter = KServeEncoder(
        endpoint_url="http://x/v1/models/m:predict", client=fake_client, expected_dim=0
    )
    vector = adapter.embed("q", "query")

    assert vector == [0.1, 0.2]


def test_kserve_reranker_predict_with_explain_via_predict_route() -> None:
    """No dedicated explain URL → POST to predict URL with parameters.explain=true.

    Matches the Phase 6 Vertex CPR reranker contract in ``ml/serving/reranker.py``
    where ``/predict`` accepts ``parameters.explain=True`` and returns both
    ``predictions`` and ``attributions`` in one round-trip.
    """
    fake_client = _fake_httpx_client(
        {
            "predictions": [0.9, 0.2],
            "attributions": [
                {"rent": 0.15, "walk_min": -0.05, "_baseline": 0.5},
                {"rent": -0.1, "walk_min": 0.08, "_baseline": 0.5},
            ],
        }
    )
    adapter = KServeReranker(
        endpoint_url="http://property-reranker.kserve-inference.svc.cluster.local/v1/models/property-reranker:predict",
        client=fake_client,
    )
    scores, attrs = adapter.predict_with_explain(
        [[1.0, 2.0], [3.0, 4.0]],
        feature_names=["rent", "walk_min"],
    )

    fake_client.post.assert_called_once()
    sent = fake_client.post.call_args.kwargs["json"]
    assert sent["instances"] == [[1.0, 2.0], [3.0, 4.0]]
    assert sent["parameters"] == {"explain": True, "feature_names": ["rent", "walk_min"]}
    assert scores == [0.9, 0.2]
    assert attrs == [
        {"rent": 0.15, "walk_min": -0.05, "_baseline": 0.5},
        {"rent": -0.1, "walk_min": 0.08, "_baseline": 0.5},
    ]


def test_kserve_reranker_predict_with_explain_via_dedicated_url() -> None:
    """When ``explain_url`` is set, the adapter calls it instead of predict URL.

    The dedicated route returns ``{attributions}`` only, so the adapter issues
    a second plain ``predict`` call to get scores. Tests verify both calls.
    """
    explain_response = _fake_httpx_client(
        {
            "attributions": [
                {"rent": 0.2, "_baseline": 0.5},
            ]
        }
    )
    # First POST = /explain (returns attributions), second POST = /predict (scores)
    explain_response.post.side_effect = [
        explain_response.post.return_value,
        _fake_httpx_client({"predictions": [0.77]}).post.return_value,
    ]
    adapter = KServeReranker(
        endpoint_url="http://r/v1/models/m:predict",
        explain_url="http://r/v1/models/m:explain",
        client=explain_response,
    )
    scores, attrs = adapter.predict_with_explain([[1.0, 2.0]], feature_names=["rent"])

    assert explain_response.post.call_count == 2
    first_call = explain_response.post.call_args_list[0]
    second_call = explain_response.post.call_args_list[1]
    # First call went to explain URL with {instances, feature_names}
    assert first_call.args[0] == "http://r/v1/models/m:explain"
    assert first_call.kwargs["json"] == {"instances": [[1.0, 2.0]], "feature_names": ["rent"]}
    # Second call went to predict URL (plain predict for scores)
    assert second_call.args[0] == "http://r/v1/models/m:predict"
    assert second_call.kwargs["json"] == {"instances": [[1.0, 2.0]]}
    assert scores == [0.77]
    assert attrs == [{"rent": 0.2, "_baseline": 0.5}]


def test_kserve_reranker_predict_with_explain_degrades_when_attrs_missing() -> None:
    """MLServer LightGBM runtime ignores ``parameters.explain=true`` and returns
    scores only. Adapter must not raise — it returns empty attribution dicts so
    the ``/search?explain=true`` path stays 200 with attributions=None per row.
    """
    fake_client = _fake_httpx_client({"predictions": [0.5, 0.6]})
    adapter = KServeReranker(endpoint_url="http://r/v1/models/m:predict", client=fake_client)
    scores, attrs = adapter.predict_with_explain(
        [[1.0, 2.0], [3.0, 4.0]],
        feature_names=["rent", "walk_min"],
    )

    assert scores == [0.5, 0.6]
    assert attrs == [{}, {}]  # empty per-instance dicts (graceful degradation)


def test_kserve_reranker_predict_with_explain_empty_instances_short_circuits() -> None:
    fake_client = _fake_httpx_client({})
    adapter = KServeReranker(endpoint_url="http://r/", client=fake_client)
    scores, attrs = adapter.predict_with_explain([], feature_names=[])
    assert scores == []
    assert attrs == []
    fake_client.post.assert_not_called()


def test_kserve_reranker_predict_with_explain_v2_degrades_to_predict_only() -> None:
    """Phase 7 B19 regression — KServe MLServer v2 stock LightGBM runtime
    rejects ``parameters.explain=true`` (returns 422). The adapter must
    detect the v2 URL and fall back to a plain v2 predict + empty
    attribution dicts so ``/search?explain=true`` stays 200 instead of
    propagating the 422 to the client.
    """
    # v2 predict response shape per Open Inference Protocol: outputs[].data is
    # a flat float list (predictions extractor handles this for is_v2 path).
    fake_client = _fake_httpx_client({"outputs": [{"name": "scores", "data": [0.5, 0.2]}]})

    adapter = KServeReranker(
        endpoint_url="http://r/v2/models/property-reranker/infer",
        client=fake_client,
    )
    scores, attrs = adapter.predict_with_explain(
        [[1.0, 2.0], [3.0, 4.0]], feature_names=["rent", "walk_min"]
    )

    # Exactly one POST: the v2 predict call (no explain payload sent).
    fake_client.post.assert_called_once()
    sent_json = fake_client.post.call_args.kwargs["json"]
    # The v2 payload must NOT contain `parameters.explain` (rejected by stock LGBServer).
    assert "parameters" not in sent_json
    assert sent_json == {
        "inputs": [
            {
                "name": "input-0",
                "shape": [2, 2],
                "datatype": "FP64",
                "data": [1.0, 2.0, 3.0, 4.0],
            }
        ]
    }
    assert scores == [0.5, 0.2]
    # Attributions degrade to empty dicts so ranking.py emits attributions=None
    # per row (caller treats None as "explain unsupported by container").
    assert attrs == [{}, {}]


def test_kserve_reranker_satisfies_reranker_explainer_protocol() -> None:
    """Structural check matching ``ranking.py``'s ``hasattr(reranker,
    'predict_with_explain')`` gate: KServeReranker must expose both ``predict``
    and ``predict_with_explain`` so services can opt into the explain path.
    """
    adapter = KServeReranker(endpoint_url="http://r/")
    assert callable(getattr(adapter, "predict", None))
    assert callable(getattr(adapter, "predict_with_explain", None))


def test_kserve_encoder_rejects_html_error_page_as_non_json() -> None:
    """Envoy / Istio 502 often serves HTML. ``response.json()`` on HTML raises
    ``json.JSONDecodeError`` (a ``ValueError``), which previously propagated
    as an opaque traceback. Now it surfaces as a ``RuntimeError`` with the
    HTML body preview + kubectl hint.
    """
    fake_response = MagicMock()
    fake_response.status_code = 502
    fake_response.text = "<html><body>upstream connect error</body></html>"
    fake_response.json.side_effect = json.JSONDecodeError("Expecting value", "<html>", 0)
    fake_response.headers = {"content-type": "text/html; charset=utf-8"}
    fake_response.raise_for_status.return_value = None
    fake_client = MagicMock()
    fake_client.post.return_value = fake_response

    adapter = KServeEncoder(
        endpoint_url="http://property-encoder.kserve-inference.svc.cluster.local/predict",
        client=fake_client,
        expected_dim=0,
    )
    import pytest as _pytest

    with _pytest.raises(RuntimeError, match="non-JSON response"):
        adapter.embed("query", "query")


def test_kserve_encoder_rejects_empty_embedding_vector() -> None:
    fake_client = _fake_httpx_client({"predictions": [{"embedding": []}]})
    adapter = KServeEncoder(endpoint_url="http://x/predict", client=fake_client, expected_dim=0)
    import pytest as _pytest

    with _pytest.raises(ValueError, match="empty embedding"):
        adapter.embed("q", "query")


def test_kserve_encoder_enforces_768d_by_default() -> None:
    """Default ``expected_dim=768`` (EXPECTED_EMBEDDING_DIM constant) guards
    the BQ VECTOR_SEARCH contract; a 512d vector must fail loud at the
    encoder, not silently at BQ.
    """
    vec_512 = [0.01] * 512
    fake_client = _fake_httpx_client({"predictions": [{"embedding": vec_512}]})
    adapter = KServeEncoder(endpoint_url="http://x/predict", client=fake_client)  # default dim
    import pytest as _pytest

    with _pytest.raises(ValueError, match="512d embedding, expected 768d"):
        adapter.embed("q", "query")


def test_kserve_encoder_rejects_nan_in_embedding() -> None:
    fake_client = _fake_httpx_client({"predictions": [{"embedding": [0.1, float("nan"), 0.3]}]})
    adapter = KServeEncoder(endpoint_url="http://x/predict", client=fake_client, expected_dim=0)
    import pytest as _pytest

    with _pytest.raises(ValueError, match="NaN at index 1"):
        adapter.embed("q", "query")


def test_kserve_encoder_rejects_inf_in_embedding() -> None:
    fake_client = _fake_httpx_client({"predictions": [{"embedding": [0.1, float("inf"), 0.3]}]})
    adapter = KServeEncoder(endpoint_url="http://x/predict", client=fake_client, expected_dim=0)
    import pytest as _pytest

    with _pytest.raises(ValueError, match="inf at index 1"):
        adapter.embed("q", "query")


def test_kserve_reranker_rejects_score_count_mismatch() -> None:
    """Ranker contract: one score per instance. A shortfall would IndexError
    later in ranking.py when zipping with candidates. Fail loud here with
    the exact shape delta.
    """
    fake_client = _fake_httpx_client({"predictions": [0.9]})  # only 1 score
    adapter = KServeReranker(endpoint_url="http://x/predict", client=fake_client)
    import pytest as _pytest

    with _pytest.raises(ValueError, match="returned 1 scores for 3 instances"):
        adapter.predict([[1.0], [2.0], [3.0]])  # 3 instances, got 1 score


def test_kserve_reranker_predict_with_explain_logs_count_mismatch_and_degrades(
    caplog,
) -> None:
    """Attribution count mismatch must be logged at ERROR level with the exact
    delta, even though the final result degrades to empty dicts (preserving
    200 on ``/search?explain=true``). This separates "runtime ignored explain"
    (no attributions key at all) from "runtime returned wrong-length array"
    (off-by-one bug in the container).
    """
    import logging as _logging

    fake_client = _fake_httpx_client(
        {
            "predictions": [0.5, 0.6],
            # 3 attribution rows for 2 instances — off-by-one bug
            "attributions": [
                {"rent": 0.1, "_baseline": 0.5},
                {"rent": 0.2, "_baseline": 0.5},
                {"rent": 0.3, "_baseline": 0.5},
            ],
        }
    )
    adapter = KServeReranker(endpoint_url="http://r/predict", client=fake_client)
    with caplog.at_level(_logging.ERROR, logger="app.kserve_prediction"):
        scores, attrs = adapter.predict_with_explain([[1.0], [2.0]], feature_names=["rent"])

    assert scores == [0.5, 0.6]
    assert attrs == [{}, {}]  # degraded
    assert any(
        "COUNT_MISMATCH" in record.message and "attributions.len=3" in record.message
        for record in caplog.records
    ), f"Expected COUNT_MISMATCH ERROR log; got: {[r.message for r in caplog.records]}"


def test_kserve_reranker_parses_v2_attributions_output() -> None:
    """V2 Open Inference: attributions come back as a named output with dict-rows data.

    The stock KServe LightGBM runtime (``/v2/models/<name>/infer``) does
    NOT return attributions — that's the B19 degrade path. But a custom
    v2 server (Vertex CPR built on the OIP ``/explain`` endpoint) can,
    and the ``_extract_attributions`` parser must handle the OIP shape.
    Wire it via ``explain_url`` so the predict_with_explain dispatch
    actually hits this path.
    """
    fake_client = _fake_httpx_client(
        {
            "outputs": [
                {"name": "predictions", "data": [0.5]},
                {
                    "name": "attributions",
                    "data": [{"rent": 0.3, "_baseline": 0.2}],
                },
            ]
        }
    )
    adapter = KServeReranker(
        endpoint_url="http://r/v2/models/m/infer",
        explain_url="http://r/v2/models/m/explain",
        client=fake_client,
    )
    # Stub the follow-up scores fetch (predict route is a separate call when
    # using explain_url; mock returns scalar predictions in v1 shape).
    adapter.predict = lambda instances: [0.5]  # type: ignore[method-assign]
    scores, attrs = adapter.predict_with_explain([[1.0]], feature_names=["rent"])

    assert scores == [0.5]
    assert attrs == [{"rent": 0.3, "_baseline": 0.2}]
