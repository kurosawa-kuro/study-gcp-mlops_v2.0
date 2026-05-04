"""GCP resource name constants — single source of truth.

複数モジュールが同じリソース名を独立に hardcode していたため、新リソース
追加時に drift が発生する事故が起きていた。本モジュールに集約することで、
追加 / リネーム時の更新箇所を 1 つに固定する。
"""

from __future__ import annotations

VERTEX_ENDPOINTS: list[str] = [
    "property-encoder-endpoint",
    "property-reranker-endpoint",
]

BUCKET_SUFFIXES: list[str] = ["models", "artifacts", "pipeline-root", "meili-data"]

GKE_CLUSTER_NAME_DEFAULT = "hybrid-search"
MEILI_SERVICE_NAME_DEFAULT = "meili-search"

VERTEX_MODEL_NAMES: list[str] = ["property-encoder", "property-reranker"]
