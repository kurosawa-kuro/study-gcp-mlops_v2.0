"""Pin scripts/lib/gcp_resources.py — リソース名 single source.

複数モジュールが独立に hardcode していた値を本モジュールに集約することで
drift を防ぐ。値そのものを pin することで、誤った変更 (e.g. typo /
順序入れ替え) を CI で即検出する。
"""

from __future__ import annotations

from scripts.lib.gcp_resources import (
    BUCKET_SUFFIXES,
    GKE_CLUSTER_NAME_DEFAULT,
    MEILI_SERVICE_NAME_DEFAULT,
    VERTEX_ENDPOINTS,
    VERTEX_MODEL_NAMES,
)


def test_vertex_endpoints_pin() -> None:
    assert VERTEX_ENDPOINTS == [
        "property-encoder-endpoint",
        "property-reranker-endpoint",
    ]


def test_bucket_suffixes_pin() -> None:
    assert BUCKET_SUFFIXES == ["models", "artifacts", "pipeline-root", "meili-data"]


def test_default_names_pin() -> None:
    assert GKE_CLUSTER_NAME_DEFAULT == "hybrid-search"
    assert MEILI_SERVICE_NAME_DEFAULT == "meili-search"


def test_vertex_model_names_pin() -> None:
    assert VERTEX_MODEL_NAMES == ["property-encoder", "property-reranker"]


def test_endpoint_names_have_endpoint_suffix() -> None:
    """``VERTEX_ENDPOINTS`` の値はすべて ``-endpoint`` で終わる。

    Vertex AI の "endpoint shell" リソース ID と、Vertex Model Display 名
    (``property-encoder`` 等、suffix なし) を取り違えるとリソースが見つから
    ない事故が起きる (Phase 7 Run 5 で観測)。型としても文字列だが、
    suffix で意味を区別する規約を pin する。
    """
    for ep in VERTEX_ENDPOINTS:
        assert ep.endswith("-endpoint"), f"{ep!r} must end with '-endpoint'"


def test_model_names_no_endpoint_suffix() -> None:
    """``VERTEX_MODEL_NAMES`` の値は ``-endpoint`` で終わらない。"""
    for mn in VERTEX_MODEL_NAMES:
        assert not mn.endswith("-endpoint"), f"{mn!r} must NOT end with '-endpoint'"
