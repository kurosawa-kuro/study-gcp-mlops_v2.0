"""SearchBuilder canonical wiring (Phase 7 W2-8 完了後).

W2-8 で BQ semantic / BQ feature fetcher の互換レイヤを撤去し、Phase 7 は
Vertex Vector Search + Feature Online Store の 1 経路に収束した。本 test は:

- ``_build_vertex_vector_search`` が settings から
  ``VertexVectorSearchSemanticSearch`` を組み立てる
- 同 ``vertex_vector_search_index_endpoint_id`` / ``deployed_index_id`` の
  片方でも空なら ``RuntimeError`` で fail-loud (silent fallback はしない)
- ``resolve_feature_fetcher`` が ``FeatureOnlineStoreFetcher`` を組み立てる
- 同 ``vertex_feature_online_store_id`` / ``view_id`` / ``endpoint`` の
  どれか欠ければ ``RuntimeError`` で fail-loud
- fully-qualified endpoint resource name (Terraform output 直流し) でも
  そのまま受理する

を pin する。canonical 経路の config が live ConfigMap で抜けたとき silent
で 503 にならず container build 段で即落ちることが本 phase の安全契約。
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.container.search import SearchBuilder
from app.services.adapters.feature_online_store_fetcher import FeatureOnlineStoreFetcher
from app.services.adapters.vertex_vector_search_semantic_search import (
    VertexVectorSearchSemanticSearch,
)
from app.settings import ApiSettings


class _FakeContext:
    def __init__(self, settings: ApiSettings) -> None:
        self._settings = settings
        self._logger = logging.getLogger("test.search_builder")

    def _bigquery(self) -> Any:
        return None


def _settings(**overrides: object) -> ApiSettings:
    base: dict[str, object] = {
        "project_id": "mlops-test",
        "vertex_location": "asia-northeast1",
        "enable_search": True,
        "vertex_vector_search_index_endpoint_id": "98765",
        "vertex_vector_search_deployed_index_id": "property_embeddings_v3",
        "vertex_feature_online_store_id": "property_features_store",
        "vertex_feature_view_id": "property_features_view",
        "vertex_feature_online_store_endpoint": "abc.asia-northeast1-fos.googleapis.com",
        "meili_base_url": "",
        "kserve_encoder_url": "",
        "kserve_reranker_url": "",
        "ranking_log_topic": "",
        "feedback_topic": "",
        "retrain_topic": "",
    }
    base.update(overrides)
    return ApiSettings(**base)  # type: ignore[arg-type]


def _builder(settings: ApiSettings) -> SearchBuilder:
    return SearchBuilder(_FakeContext(settings))


# ----------------------------------------------------------------------------
# Vertex Vector Search semantic backend (canonical)
# ----------------------------------------------------------------------------


def test_build_vertex_vector_search_assembles_endpoint_resource_name() -> None:
    builder = _builder(_settings())
    semantic = builder._build_vertex_vector_search()
    assert isinstance(semantic, VertexVectorSearchSemanticSearch)
    assert semantic._index_endpoint_name == (
        "projects/mlops-test/locations/asia-northeast1/indexEndpoints/98765"
    )
    assert semantic._deployed_index_id == "property_embeddings_v3"


def test_build_vertex_vector_search_accepts_fully_qualified_endpoint_name() -> None:
    """Terraform output may already contain the full resource name."""
    builder = _builder(
        _settings(
            vertex_vector_search_index_endpoint_id=(
                "projects/mlops-test/locations/asia-northeast1/indexEndpoints/98765"
            ),
        )
    )
    semantic = builder._build_vertex_vector_search()
    assert semantic._index_endpoint_name == (
        "projects/mlops-test/locations/asia-northeast1/indexEndpoints/98765"
    )


def test_build_vertex_vector_search_fails_loud_when_endpoint_missing() -> None:
    builder = _builder(_settings(vertex_vector_search_index_endpoint_id=""))
    with pytest.raises(RuntimeError, match="Vertex Vector Search config is incomplete"):
        builder._build_vertex_vector_search()


def test_build_vertex_vector_search_fails_loud_when_deployed_id_missing() -> None:
    builder = _builder(_settings(vertex_vector_search_deployed_index_id=""))
    with pytest.raises(RuntimeError, match="Vertex Vector Search config is incomplete"):
        builder._build_vertex_vector_search()


# ----------------------------------------------------------------------------
# Feature Online Store fetcher (canonical)
# ----------------------------------------------------------------------------


def test_resolve_feature_fetcher_returns_fos_when_fully_configured() -> None:
    fetcher = _builder(_settings()).resolve_feature_fetcher()
    assert isinstance(fetcher, FeatureOnlineStoreFetcher)
    assert fetcher._feature_view == (
        "projects/mlops-test/locations/asia-northeast1/featureOnlineStores/"
        "property_features_store/featureViews/property_features_view"
    )


def test_resolve_feature_fetcher_fails_loud_when_store_missing() -> None:
    builder = _builder(_settings(vertex_feature_online_store_id=""))
    with pytest.raises(RuntimeError, match="Feature Online Store config is incomplete"):
        builder.resolve_feature_fetcher()


def test_resolve_feature_fetcher_fails_loud_when_view_missing() -> None:
    builder = _builder(_settings(vertex_feature_view_id=""))
    with pytest.raises(RuntimeError, match="Feature Online Store config is incomplete"):
        builder.resolve_feature_fetcher()


def test_resolve_feature_fetcher_fails_loud_when_endpoint_missing() -> None:
    builder = _builder(_settings(vertex_feature_online_store_endpoint=""))
    with pytest.raises(RuntimeError, match="Feature Online Store config is incomplete"):
        builder.resolve_feature_fetcher()
