"""Pin scripts/lib/config.py — single source for ConfigMap schema.

W2-8 で互換レイヤを撤去後、ConfigMap は Vertex Vector Search / Feature
Online Store の resource ID + endpoint だけを持つ (8 keys)。本 test は:

1. CONFIGMAP_KEYS が deployment.yaml が要求する全キーを覆う
2. generate_configmap_data() の出力が all-string で必須 3 引数を埋める
3. render_configmap_yaml(with_header=True) が
   `infra/manifests/search-api/configmap.example.yaml` と byte 一致

を pin する。drift しそうになると CI で即弾く。
"""

from __future__ import annotations

from pathlib import Path

from scripts.lib.config import CONFIGMAP_KEYS, generate_configmap_data, render_configmap_yaml

EXPECTED_KEYS = (
    "project_id",
    "models_bucket",
    "meili_base_url",
    "vertex_vector_search_index_endpoint_id",
    "vertex_vector_search_deployed_index_id",
    "vertex_feature_online_store_id",
    "vertex_feature_view_id",
    "vertex_feature_online_store_endpoint",
)


def test_configmap_keys_pin() -> None:
    assert tuple(CONFIGMAP_KEYS) == EXPECTED_KEYS


def test_generate_configmap_data_returns_all_keys_strings() -> None:
    data = generate_configmap_data(
        project_id="p",
        models_bucket="b",
        meili_base_url="u",
    )
    assert set(data.keys()) == set(EXPECTED_KEYS)
    assert all(isinstance(v, str) for v in data.values())


def test_committed_example_defaults_are_empty_for_vertex_resources() -> None:
    """Pre-live committed example has empty Vertex IDs — overlay fills them."""
    data = generate_configmap_data(project_id="p", models_bucket="b", meili_base_url="u")
    for k in (
        "vertex_vector_search_index_endpoint_id",
        "vertex_vector_search_deployed_index_id",
        "vertex_feature_online_store_id",
        "vertex_feature_view_id",
        "vertex_feature_online_store_endpoint",
    ):
        assert data[k] == ""


def test_generate_configmap_data_passes_through_live_vertex_outputs() -> None:
    data = generate_configmap_data(
        project_id="p",
        models_bucket="b",
        meili_base_url="u",
        vertex_vector_search_index_endpoint_id="idx-endpoint",
        vertex_vector_search_deployed_index_id="deploy-1",
        vertex_feature_online_store_id="store-1",
        vertex_feature_view_id="view-1",
        vertex_feature_online_store_endpoint="store.example.com",
    )
    assert data["vertex_vector_search_index_endpoint_id"] == "idx-endpoint"
    assert data["vertex_vector_search_deployed_index_id"] == "deploy-1"
    assert data["vertex_feature_online_store_id"] == "store-1"
    assert data["vertex_feature_view_id"] == "view-1"
    assert data["vertex_feature_online_store_endpoint"] == "store.example.com"


def test_render_committed_form_matches_example_yaml() -> None:
    """with_header=True must render byte-for-byte the committed example."""
    repo_root = Path(__file__).resolve().parents[3]
    committed = (
        repo_root / "infra" / "manifests" / "search-api" / "configmap.example.yaml"
    ).read_text(encoding="utf-8")
    data = generate_configmap_data(
        project_id="mlops-dev-a",
        models_bucket="mlops-dev-a-models",
        meili_base_url="https://meili-search-XXXXX-an.a.run.app",
    )
    assert render_configmap_yaml(data, with_header=True) == committed


def test_render_runtime_form_omits_header() -> None:
    """with_header=False is the runtime overlay form (deploy_all step 9)."""
    data = generate_configmap_data(project_id="p", models_bucket="b", meili_base_url="https://x")
    out = render_configmap_yaml(data, with_header=False)
    assert "AUTO-GENERATED" not in out
    # Each key is present once
    for k in EXPECTED_KEYS:
        assert f"  {k}:" in out
    # Empty values are double-quoted (kubectl tolerates `key: ""`, not `key:`)
    assert '  vertex_feature_view_id: ""\n' in out


def test_render_values_are_double_quoted() -> None:
    """All values use YAML double-quotes — required for empty strings."""
    data = generate_configmap_data(project_id="p", models_bucket="b", meili_base_url="u")
    out = render_configmap_yaml(data, with_header=False)
    # Every data line should match `  KEY: "VALUE"`
    for k in EXPECTED_KEYS:
        # The line begins with two spaces and ends with `"\n`.
        # Test for the simplest signature:
        assert f'  {k}: "' in out, f"{k} missing double-quote"
