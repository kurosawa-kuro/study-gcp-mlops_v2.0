"""Smoke-test the Vertex AI Vector Search index endpoint via ``find_neighbors``.

Phase 7 Wave 2 W2-7. Wave 2 W2-1 で provision された
``module.vector_search`` の index endpoint が live で応答することを確認するための
one-off smoke。Wave 1 PR-1 で実装済の
``app/services/adapters/vertex_vector_search_semantic_search.py`` と同じ
API (``MatchingEngineIndexEndpoint.find_neighbors``) を直接叩く。

Usage (after ``make deploy-all`` and ``make ops-vertex-vector-search-smoke``)::

    PROJECT_ID=mlops-dev-a \\
    VERTEX_LOCATION=asia-northeast1 \\
    VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT_ID=projects/.../indexEndpoints/123 \\
    VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID=property_embeddings_v3 \\
    python -m scripts.ops.vertex.vector_search

Exit codes:
    0  — endpoint returned at least one neighbor
    1  — config error / endpoint not provisioned / IAM / 0 neighbors
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from scripts._common import env, fail

INFRA = Path(__file__).resolve().parents[3] / "infra" / "terraform" / "environments" / "dev"
DEFAULT_PROBE_DIM = 768


def _terraform_output_map() -> dict[str, str]:
    from scripts._common import run

    proc = run(["terraform", f"-chdir={INFRA}", "output", "-json"], capture=True, check=False)
    if proc.returncode != 0:
        return {}
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    resolved: dict[str, str] = {}
    for key, meta in payload.items():
        value = meta.get("value", "") if isinstance(meta, dict) else ""
        resolved[key] = str(value or "")
    return resolved


def _build_probe_vector(dim: int = DEFAULT_PROBE_DIM) -> list[float]:
    """Deterministic probe vector. The smoke goal is "endpoint replied",
    not "neighbors are semantically meaningful" — content is arbitrary."""
    return [1.0 / (i + 1) for i in range(dim)]


def main() -> int:
    project_id = env("PROJECT_ID")
    if not project_id:
        return fail("vertex-vector-search: PROJECT_ID is required")
    region = env("VERTEX_LOCATION", env("REGION", "asia-northeast1"))
    outputs = _terraform_output_map()
    endpoint_id = env(
        "VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT_ID",
        outputs.get("vector_search_index_endpoint_id", ""),
    )
    deployed_index_id = env(
        "VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID",
        outputs.get("vector_search_deployed_index_id", ""),
    )
    if not endpoint_id:
        return fail(
            "vertex-vector-search: VERTEX_VECTOR_SEARCH_INDEX_ENDPOINT_ID is required "
            "(= module.vector_search.index_endpoint_id Terraform output, "
            "set enable_vector_search=true and apply first)"
        )
    if not deployed_index_id:
        return fail(
            "vertex-vector-search: VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID is required "
            "(= module.vector_search.deployed_index_id Terraform output)"
        )
    num_neighbors_str = os.environ.get("NUM_NEIGHBORS", "5")
    try:
        num_neighbors = int(num_neighbors_str)
    except ValueError:
        return fail(f"vertex-vector-search: NUM_NEIGHBORS must be int, got {num_neighbors_str!r}")

    try:
        from google.cloud import aiplatform  # type: ignore[import-untyped]
    except ImportError:
        return fail("vertex-vector-search: google-cloud-aiplatform required.")

    aiplatform.init(project=project_id, location=region)
    endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=endpoint_id)

    probe = _build_probe_vector()
    try:
        response = endpoint.find_neighbors(
            deployed_index_id=deployed_index_id,
            queries=[probe],
            num_neighbors=num_neighbors,
        )
    except Exception as exc:
        return fail(f"vertex-vector-search: find_neighbors failed: {exc}")

    if not response or not response[0]:
        return fail(
            "vertex-vector-search: endpoint returned 0 neighbors "
            "(index may be empty — run scripts/setup/backfill_vector_search_index.py first)"
        )

    print(
        f"[vertex-vector-search] OK — endpoint={endpoint_id} "
        f"deployed_index={deployed_index_id} returned {len(response[0])} neighbors"
    )
    for n in response[0]:
        # Dataclass and proto attribute names differ across SDK versions; use getattr defensively.
        nid = getattr(n, "id", None) or getattr(n, "datapoint_id", None) or "?"
        dist = getattr(n, "distance", None)
        print(f"  - id={nid} distance={dist}")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    raise SystemExit(main())
