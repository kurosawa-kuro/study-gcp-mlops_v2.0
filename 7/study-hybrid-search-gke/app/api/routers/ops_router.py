"""Developer-facing ops APIs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.schemas.ops import (
    DestroyCheckFindingResponse,
    DestroyCheckResponse,
    DestroyCheckSummaryResponse,
    RecentTrainingRunsResponse,
    SearchVolumeResponse,
    TrainingRunSummaryResponse,
)
from scripts._common import env
from scripts.ops.destroy_check import collect_findings

router = APIRouter(prefix="/ops")
ROOT = Path(__file__).resolve().parents[3]
SEARCH_VOLUME_SQL = ROOT / "scripts" / "sql" / "search_volume.sql"
RUNS_RECENT_SQL = ROOT / "scripts" / "sql" / "runs_recent.sql"


def _run_bq_query(*, project_id: str, sql_path: Path) -> list[dict[str, object | None]]:
    proc = subprocess.run(
        [
            "bq",
            f"--project_id={project_id}",
            "query",
            "--use_legacy_sql=false",
            "--format=prettyjson",
        ],
        input=sql_path.read_text(encoding="utf-8"),
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(detail or f"bq query failed: {sql_path.name}")
    payload = json.loads((proc.stdout or "[]").strip() or "[]")
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected bq payload: {sql_path.name}")
    return payload


@router.get("/destroy-check", response_model=DestroyCheckResponse)
def destroy_check(
    project_id: str = Query(default=env("PROJECT_ID", "mlops-dev-a")),
    region: str = Query(default=env("REGION", "asia-northeast1")),
    vertex_location: str = Query(default=env("VERTEX_LOCATION", env("REGION", "asia-northeast1"))),
) -> DestroyCheckResponse:
    findings = collect_findings(
        project_id=project_id,
        region=region,
        vertex_location=vertex_location,
    )
    ok = sum(1 for finding in findings if finding.severity == "OK")
    warn = sum(1 for finding in findings if finding.severity == "WARN")
    fail = sum(1 for finding in findings if finding.severity == "FAIL")
    error = sum(1 for finding in findings if finding.severity == "ERROR")
    return DestroyCheckResponse(
        project_id=project_id,
        region=region,
        vertex_location=vertex_location,
        summary=DestroyCheckSummaryResponse(
            ok=ok,
            warn=warn,
            fail=fail,
            error=error,
            passed=(fail == 0 and error == 0),
        ),
        findings=[
            DestroyCheckFindingResponse(
                label=finding.label,
                severity=finding.severity,
                items=list(finding.items),
                note=finding.note,
            )
            for finding in findings
        ],
    )


@router.get("/search-volume", response_model=SearchVolumeResponse)
def search_volume(
    project_id: str = Query(default=env("PROJECT_ID", "mlops-dev-a")),
) -> SearchVolumeResponse:
    try:
        rows = _run_bq_query(project_id=project_id, sql_path=SEARCH_VOLUME_SQL)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    row = rows[0] if rows else {}
    return SearchVolumeResponse(
        requests_24h=_as_int(row.get("n")),
        first_ts=str(row.get("first_ts")) if row.get("first_ts") is not None else None,
        last_ts=str(row.get("last_ts")) if row.get("last_ts") is not None else None,
    )


@router.get("/runs-recent", response_model=RecentTrainingRunsResponse)
def runs_recent(
    project_id: str = Query(default=env("PROJECT_ID", "mlops-dev-a")),
) -> RecentTrainingRunsResponse:
    try:
        rows = _run_bq_query(project_id=project_id, sql_path=RUNS_RECENT_SQL)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RecentTrainingRunsResponse(
        runs=[
            TrainingRunSummaryResponse(
                run_id=str(row.get("run_id") or ""),
                finished_at=str(row.get("finished_at")) if row.get("finished_at") else None,
                ndcg_at_10=_as_float(row.get("ndcg_at_10")),
                map_score=_as_float(row.get("map")),
                recall_at_20=_as_float(row.get("recall_at_20")),
                model_path=str(row.get("model_path")) if row.get("model_path") else None,
            )
            for row in rows
        ]
    )


def _as_int(value: object | None) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, str, bytes, bytearray)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _as_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str, bytes, bytearray)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
