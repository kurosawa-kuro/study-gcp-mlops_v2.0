"""Pydantic schemas for /model/* endpoints.

`/model/metrics` returns hybrid-search accuracy (NDCG@k / HitRate@k / MRR@k);
`/model/info` returns the active model artifact identifiers.
`/model/data` returns developer-facing previews of training / serving tables.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CaseMetric(BaseModel):
    name: str
    query: str
    returned: int
    relevant_total: int
    matched_in_results: int
    ndcg_at_k: float
    hit_rate_at_k: float
    mrr_at_k: float


class AccuracySummary(BaseModel):
    ndcg_at_k: float
    hit_rate_at_k: float
    mrr_at_k: float


class ModelMetricsResponse(BaseModel):
    cases_file: str
    num_cases: int
    k: int
    summary: AccuracySummary
    per_case: list[CaseMetric]


class ModelInfoResponse(BaseModel):
    encoder_endpoint: str = Field(
        description="Cluster-local URL for the KServe encoder InferenceService"
    )
    encoder_model_path: str | None = Field(
        default=None, description="Encoder model identifier (Vertex Model Registry name or URI)"
    )
    reranker_endpoint: str = Field(
        description="Cluster-local URL for the KServe reranker InferenceService"
    )
    reranker_model_path: str | None = Field(
        default=None, description="Reranker model identifier (LightGBM model.bst location)"
    )
    rerank_enabled: bool
    search_enabled: bool


class DataPreviewTable(BaseModel):
    key: str
    title: str
    description: str
    table_fqn: str
    latest_marker: str | None = None
    columns: list[str]
    rows: list[dict[str, object | None]]


class ModelDataResponse(BaseModel):
    tables: list[DataPreviewTable]
