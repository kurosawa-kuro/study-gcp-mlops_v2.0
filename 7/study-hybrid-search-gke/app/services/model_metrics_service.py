"""Model metrics service — hybrid-search 精度評価 API のドメイン実装。

`/model/metrics` ハンドラから呼ばれて、設定済みの :class:`SearchService` を
バンドル済み eval-cases (or env override) で叩き、NDCG@k / hit_rate@k /
MRR@k を計算して返す。CLI 実装 (``scripts/ops/accuracy_report.py``) は
HTTP 経由で同じ結果を再現する位置付けだが、この service は in-process で
SearchService を直接叩くので Pod 起動済の環境ではこちらが正本。

評価指標は CLI と同じ二値関連度 (relevant_property_ids 集合に含まれるか)
ベースの NDCG / Hit Rate / MRR。
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.domain.search import SearchFilters, SearchInput
from app.services.search_service import SearchService, SearchServiceUnavailable


@dataclass(frozen=True)
class EvalCase:
    """Single evaluation case loaded from JSON."""

    name: str
    query: str
    filters: SearchFilters
    top_k: int
    relevant_property_ids: tuple[str, ...]


@dataclass(frozen=True)
class CaseReport:
    name: str
    query: str
    returned: int
    relevant_total: int
    matched_in_results: int
    ndcg_at_k: float
    hit_rate_at_k: float
    mrr_at_k: float


@dataclass(frozen=True)
class AccuracyReport:
    cases_file: str
    num_cases: int
    k: int
    summary_ndcg_at_k: float
    summary_hit_rate_at_k: float
    summary_mrr_at_k: float
    per_case: tuple[CaseReport, ...]


def load_cases(path: Path) -> list[EvalCase]:
    """Parse the bundled / overridden eval-cases JSON.

    Schema: ``{"cases": [{"name", "query", "filters", "top_k",
    "relevant_property_ids"}, ...]}``. Compatible with Phase 4 / 5 sample
    files plus the Phase 7 bundle at ``app/data/accuracy_eval_cases.json``.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("cases must be a non-empty list")
    out: list[EvalCase] = []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"case[{i}] must be an object")
        query = str(row.get("query") or row.get("q") or "").strip()
        if not query:
            raise ValueError(f"case[{i}] query is required")
        relevant_raw = row.get("relevant_property_ids") or row.get("relevant_ids") or []
        if not isinstance(relevant_raw, list) or not relevant_raw:
            raise ValueError(f"case[{i}] relevant_property_ids must be a non-empty list")
        filters_raw = row.get("filters") or {}
        if not isinstance(filters_raw, dict):
            raise ValueError(f"case[{i}] filters must be an object")
        top_k_raw = row.get("top_k", row.get("limit", 20))
        out.append(
            EvalCase(
                name=str(row.get("name") or f"case-{i}"),
                query=query,
                filters=_coerce_filters(filters_raw),
                top_k=int(top_k_raw if top_k_raw is not None else 20),
                relevant_property_ids=tuple(str(x) for x in relevant_raw),
            )
        )
    return out


def _coerce_filters(raw: dict[str, object]) -> SearchFilters:
    def _as_int(v: object) -> int:
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, (int, float, str)):
            return int(v)
        raise ValueError(f"cannot coerce {type(v).__name__} to int")

    out: SearchFilters = {}
    if "max_rent" in raw:
        out["max_rent"] = _as_int(raw["max_rent"])
    if "layout" in raw:
        out["layout"] = str(raw["layout"])
    if "max_walk_min" in raw:
        out["max_walk_min"] = _as_int(raw["max_walk_min"])
    if "pet_ok" in raw:
        out["pet_ok"] = bool(raw["pet_ok"])
    if "max_age" in raw:
        out["max_age"] = _as_int(raw["max_age"])
    return out


def _dcg_binary(relevance: list[int], *, k: int) -> float:
    return sum(1.0 / math.log2(i + 1.0) for i, rel in enumerate(relevance[:k], start=1) if rel > 0)


def _ndcg_at_k(relevance: list[int], *, k: int) -> float:
    actual = _dcg_binary(relevance, k=k)
    ideal = _dcg_binary(sorted(relevance, reverse=True), k=k)
    return 0.0 if ideal == 0.0 else actual / ideal


def _hit_rate_at_k(relevance: list[int], *, k: int) -> float:
    return 1.0 if any(r > 0 for r in relevance[:k]) else 0.0


def _mrr_at_k(relevance: list[int], *, k: int) -> float:
    for i, rel in enumerate(relevance[:k], start=1):
        if rel > 0:
            return 1.0 / float(i)
    return 0.0


def default_cases_path() -> Path:
    """Bundled eval-cases location inside the python package."""
    return Path(__file__).resolve().parent.parent / "data" / "accuracy_eval_cases.json"


class ModelMetricsService:
    """Accuracy report generator over a configured SearchService.

    Stateless: pure function of (search_service, cases, k). Wired at
    startup with the same SearchService that handles ``/search`` so the
    accuracy snapshot reflects the live retrieval / rerank pipeline.
    """

    def __init__(self, *, search_service: SearchService, default_cases_file: Path) -> None:
        self._search_service = search_service
        self._default_cases_file = default_cases_file

    def evaluate(self, *, cases_file: Path | None = None, k: int = 10) -> AccuracyReport:
        if k <= 0:
            raise ValueError("k must be > 0")
        path = cases_file or self._default_cases_file
        cases = load_cases(path)
        per_case: list[CaseReport] = []
        ndcgs: list[float] = []
        hits: list[float] = []
        mrrs: list[float] = []
        for case in cases:
            request_id = uuid.uuid4().hex
            input_ = SearchInput(
                query=case.query,
                filters=case.filters,
                top_k=case.top_k,
            )
            try:
                output = self._search_service.search(request_id=request_id, input=input_)
            except SearchServiceUnavailable as exc:
                raise RuntimeError(f"search service unavailable while evaluating: {exc}") from exc
            relevance: list[int] = []
            matched = 0
            for item in output.items:
                hit = 1 if item.property_id in case.relevant_property_ids else 0
                relevance.append(hit)
                matched += hit
            ndcg = _ndcg_at_k(relevance, k=k)
            hit_rate = _hit_rate_at_k(relevance, k=k)
            mrr = _mrr_at_k(relevance, k=k)
            ndcgs.append(ndcg)
            hits.append(hit_rate)
            mrrs.append(mrr)
            per_case.append(
                CaseReport(
                    name=case.name,
                    query=case.query,
                    returned=len(output.items),
                    relevant_total=len(case.relevant_property_ids),
                    matched_in_results=matched,
                    ndcg_at_k=round(ndcg, 4),
                    hit_rate_at_k=round(hit_rate, 4),
                    mrr_at_k=round(mrr, 4),
                )
            )
        n = len(cases)
        return AccuracyReport(
            cases_file=str(path),
            num_cases=n,
            k=k,
            summary_ndcg_at_k=round(sum(ndcgs) / n, 4),
            summary_hit_rate_at_k=round(sum(hits) / n, 4),
            summary_mrr_at_k=round(sum(mrrs) / n, 4),
            per_case=tuple(per_case),
        )
