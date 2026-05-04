"""Pydantic schemas for developer-facing ops endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class DestroyCheckFindingResponse(BaseModel):
    label: str
    severity: str
    items: list[str]
    note: str = ""


class DestroyCheckSummaryResponse(BaseModel):
    ok: int
    warn: int
    fail: int
    error: int
    passed: bool


class DestroyCheckResponse(BaseModel):
    project_id: str
    region: str
    vertex_location: str
    summary: DestroyCheckSummaryResponse
    findings: list[DestroyCheckFindingResponse]


class SearchVolumeResponse(BaseModel):
    requests_24h: int
    first_ts: str | None = None
    last_ts: str | None = None


class TrainingRunSummaryResponse(BaseModel):
    run_id: str
    finished_at: str | None = None
    ndcg_at_10: float | None = None
    map_score: float | None = None
    recall_at_20: float | None = None
    model_path: str | None = None


class RecentTrainingRunsResponse(BaseModel):
    runs: list[TrainingRunSummaryResponse]
