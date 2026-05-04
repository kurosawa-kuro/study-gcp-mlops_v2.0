"""Phase 7 Wave 2 W2-6 — Vertex AI Vector Search 初回 backfill.

Wave 1 PR-3 で embed pipeline に組み込んだ VVS upsert step は **incremental
更新** (BQ MERGE 後の新規 / 更新分のみ) を担当する。それ以前に既に BQ に
溜まっている全 embedding を一度にまとめて push するための **one-off**
スクリプトが本ファイル。

実装方針 (本 phase docs/02 §4.4 W2-6):

- BQ ``feature_mart.property_embeddings`` を全件 SELECT
- ``pipeline.data_job.adapters.vertex_vector_search_writer.VertexVectorSearchWriter``
  を再利用して chunk upsert (default batch_size=500、Wave 1 PR-3 と一致)
- idempotent: ``upsert_datapoints`` は datapoint_id 単位で upsert なので
  再実行しても問題なし (Vertex Vector Search の streaming update セマンティクス)

依存: ``google-cloud-bigquery`` / ``google-cloud-aiplatform`` (どちらも
``pyproject.toml`` 既存)。

実行例 (実 GCP)::

    PROJECT_ID=mlops-dev-a \\
    VERTEX_LOCATION=asia-northeast1 \\
    VERTEX_VECTOR_SEARCH_INDEX_RESOURCE_NAME=projects/.../indexes/123 \\
    python -m scripts.setup.backfill_vector_search_index --apply

``--apply`` を付けないと dry-run (BQ scan のみ、VVS upsert は呼ばない) で
件数だけ表示する。

unit test (本ファイルが直接 import 可能なよう、SDK 呼び出しは ``main()``
内に閉じ込め、モジュール load 時には外部 SDK を import しない)。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts._common import env, run

DEFAULT_BATCH_SIZE = 500
INFRA = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "environments" / "dev"


@dataclass(frozen=True)
class BackfillSpec:
    project_id: str
    location: str
    index_resource_name: str
    embeddings_table: str
    batch_size: int


def _terraform_output_map() -> dict[str, str]:
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


def build_spec() -> BackfillSpec:
    """Resolve the backfill spec from env (no SDK calls).

    Raises ``ValueError`` if any required env is missing so the unit test
    can verify the resolution logic without a live GCP connection.
    """
    project_id = env("PROJECT_ID")
    if not project_id:
        raise ValueError("PROJECT_ID is required")
    location = env("VERTEX_LOCATION", "asia-northeast1")
    outputs = _terraform_output_map()
    index_resource_name = env(
        "VERTEX_VECTOR_SEARCH_INDEX_RESOURCE_NAME",
        outputs.get("vector_search_index_resource_name", ""),
    )
    if not index_resource_name:
        raise ValueError(
            "VERTEX_VECTOR_SEARCH_INDEX_RESOURCE_NAME is required "
            "(= module.vector_search.index_resource_name in Terraform outputs)"
        )
    embeddings_table = env(
        "VERTEX_VECTOR_SEARCH_BACKFILL_TABLE",
        f"{project_id}.feature_mart.property_embeddings",
    )
    batch_size_str = env("VERTEX_VECTOR_SEARCH_UPSERT_BATCH_SIZE", str(DEFAULT_BATCH_SIZE))
    try:
        batch_size = int(batch_size_str)
    except ValueError as exc:
        raise ValueError(
            f"VERTEX_VECTOR_SEARCH_UPSERT_BATCH_SIZE must be int, got {batch_size_str!r}"
        ) from exc
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return BackfillSpec(
        project_id=project_id,
        location=location,
        index_resource_name=index_resource_name,
        embeddings_table=embeddings_table,
        batch_size=batch_size,
    )


def _bq_iter_rows(spec: BackfillSpec) -> Iterable[dict[str, Any]]:
    """Stream rows from ``feature_mart.property_embeddings`` (lazy import)."""
    from google.cloud import bigquery  # type: ignore[import-untyped]  # lazy

    client = bigquery.Client(project=spec.project_id)
    query = (
        f"SELECT property_id, embedding FROM `{spec.embeddings_table}` "
        "WHERE embedding IS NOT NULL AND ARRAY_LENGTH(embedding) > 0"
    )
    return client.query(query).result()  # type: ignore[no-any-return]


def _to_datapoints(rows: Iterable[dict[str, Any]]) -> list[Any]:
    """Map BQ rows → ``EmbeddingDatapoint``. Lazy import to keep tests light."""
    from pipeline.data_job.ports.vector_search_writer import EmbeddingDatapoint  # lazy

    return [
        EmbeddingDatapoint(property_id=str(r["property_id"]), embedding=list(r["embedding"]))
        for r in rows
    ]


def _build_writer(spec: BackfillSpec) -> Any:
    from pipeline.data_job.adapters.vertex_vector_search_writer import (  # lazy
        VertexVectorSearchWriter,
    )

    return VertexVectorSearchWriter(
        index_resource_name=spec.index_resource_name,
        project=spec.project_id,
        location=spec.location,
        batch_size=spec.batch_size,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually upsert into Vertex Vector Search. Without this flag the script just "
        "scans BQ and prints the row count (dry-run).",
    )
    args = parser.parse_args(argv)

    spec = build_spec()
    print(
        f"[backfill_vector_search_index] project={spec.project_id} "
        f"location={spec.location} index={spec.index_resource_name} "
        f"table={spec.embeddings_table} batch_size={spec.batch_size}",
        file=sys.stderr,
    )

    rows = list(_bq_iter_rows(spec))
    print(f"[backfill_vector_search_index] BQ rows: {len(rows)}", file=sys.stderr)
    if not args.apply:
        print(
            "[backfill_vector_search_index] dry-run — re-run with --apply to upsert",
            file=sys.stderr,
        )
        return 0

    datapoints = _to_datapoints(rows)
    writer = _build_writer(spec)
    writer.upsert(datapoints)
    print(
        f"[backfill_vector_search_index] upserted {len(datapoints)} datapoints "
        f"into {spec.index_resource_name}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    sys.exit(main())
