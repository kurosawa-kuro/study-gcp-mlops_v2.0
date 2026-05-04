"""ConfigMap schema — single source for sync_configmap.py and deploy_all overlay.

Phase 7 W2-5 で `scripts/setup/deploy_all.py::_run_overlay_configmap` と
`scripts/ci/sync_configmap.py::render` が独立に key を手書きしていた drift
事故への構造的対策として、本モジュールがキー列・default 値・YAML 出力を
**唯一定義**する。新キー追加時の更新箇所を 1 つに固定する。

W2-8 で BQ semantic / BQ feature fetcher の互換レイヤを撤去後、ConfigMap は
Vertex Vector Search / Feature Online Store の resource ID / endpoint だけを
持つ。`semantic_backend` / `feature_fetcher_backend` のような backend 切替
selector はもう存在しない (canonical 1 経路に収束)。

I/O は行わない (subprocess / network / filesystem 不可) — 純粋データ層。
"""

from __future__ import annotations

# Group ordering preserves blank-line layout in the committed
# `infra/manifests/search-api/configmap.example.yaml`. Groups separate
# environment-specific values (project / bucket / meili URL) from Vertex
# resource identifiers (vector search / feature online store).
_GROUPS: list[list[str]] = [
    ["project_id", "models_bucket", "meili_base_url"],
    [
        "vertex_vector_search_index_endpoint_id",
        "vertex_vector_search_deployed_index_id",
    ],
    [
        "vertex_feature_online_store_id",
        "vertex_feature_view_id",
        "vertex_feature_online_store_endpoint",
    ],
]

# Default value applied when generate_configmap_data() is not overridden.
# All Vertex resource identifiers default to "" because the committed example
# is checked in before live `terraform apply`. `make deploy-all` resolves
# Terraform outputs and overlays the live values via configmap_overlay.
_DEFAULTS: dict[str, str] = {
    "vertex_vector_search_index_endpoint_id": "",
    "vertex_vector_search_deployed_index_id": "",
    "vertex_feature_online_store_id": "",
    "vertex_feature_view_id": "",
    "vertex_feature_online_store_endpoint": "",
}

CONFIGMAP_KEYS: list[str] = [k for group in _GROUPS for k in group]


def generate_configmap_data(
    project_id: str,
    models_bucket: str,
    meili_base_url: str,
    *,
    vertex_vector_search_index_endpoint_id: str = "",
    vertex_vector_search_deployed_index_id: str = "",
    vertex_feature_online_store_id: str = "",
    vertex_feature_view_id: str = "",
    vertex_feature_online_store_endpoint: str = "",
) -> dict[str, str]:
    """Build the search-api ConfigMap `data` mapping.

    Caller-supplied values: ``project_id``, ``models_bucket``,
    ``meili_base_url`` (environment-specific, resolved at runtime by
    deploy_all overlay). Vertex resource IDs / endpoints come from
    ``terraform output`` and pass through verbatim. Empty values render as
    YAML ``""`` so the committed example stays apply-able pre-live.
    """
    data: dict[str, str] = {
        "project_id": project_id,
        "models_bucket": models_bucket,
        "meili_base_url": meili_base_url,
    }
    for k, v in _DEFAULTS.items():
        data[k] = v
    data["vertex_vector_search_index_endpoint_id"] = vertex_vector_search_index_endpoint_id
    data["vertex_vector_search_deployed_index_id"] = vertex_vector_search_deployed_index_id
    data["vertex_feature_online_store_id"] = vertex_feature_online_store_id
    data["vertex_feature_view_id"] = vertex_feature_view_id
    data["vertex_feature_online_store_endpoint"] = vertex_feature_online_store_endpoint
    return data


def render_configmap_yaml(data: dict[str, str], *, with_header: bool = False) -> str:
    """Render the ConfigMap as a kubectl-applicable YAML string.

    `with_header=True` emits the AUTO-GENERATED notice + group blank lines
    (used by `scripts/ci/sync_configmap.py` for the committed file).
    `with_header=False` emits the bare apiVersion/kind/metadata/data block
    suitable for `kubectl apply -f -` (used by deploy_all overlay).

    All values are double-quoted so empty strings remain valid YAML
    (`""`) — bare empty values would be parsed as `null` by some clients.
    """
    parts: list[str] = []
    if with_header:
        parts.append(
            "# AUTO-GENERATED from env/config/setting.yaml — do NOT edit by hand.\n"
            "# Run `make sync-configmap` to regenerate after changing setting.yaml.\n"
            "# `meili_base_url` is environment-specific (Cloud Run URL) — overlay\n"
            "# the real value before `make apply-manifests`.\n"
            "#\n"
            "# Phase 7 W2-8 完了後 ConfigMap は Vertex Vector Search / Feature\n"
            "# Online Store の resource ID / endpoint だけを持つ。`semantic_backend`\n"
            "# / `feature_fetcher_backend` のような backend 切替 selector は撤去済。\n"
        )
    parts.append(
        "apiVersion: v1\n"
        "kind: ConfigMap\n"
        "metadata:\n"
        "  name: search-api-config\n"
        "  namespace: search\n"
        "data:\n"
    )
    for i, group in enumerate(_GROUPS):
        if with_header and i > 0:
            parts.append("\n")
        for key in group:
            value = data.get(key, _DEFAULTS.get(key, ""))
            # !r → single-quoted Python repr; replace produces YAML
            # double-quoted form (matches existing committed file byte-for-byte)
            parts.append(f"  {key}: {value!r}\n".replace("'", '"'))
    return "".join(parts)
