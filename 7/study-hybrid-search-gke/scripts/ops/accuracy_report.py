"""Lightweight ranking accuracy report for local and GCP /search."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from scripts._common import fail, resolve_api_target


@dataclass(frozen=True)
class EvalCase:
    name: str
    query: str
    filters: dict
    top_k: int
    relevant_property_ids: list[str]


def _default_cases_path() -> Path:
    """Resolve the default eval cases JSON path.

    Phase 7 runtime: ``<repo>/app/data/accuracy_eval_cases.json`` (committed in
    repo). 旧 fallback path (``scripts/ops/data/accuracy_eval_cases.sample.json``
    と ``parents[5]/docs/accuracy_eval_cases.common.json``) は Phase 4 までの
    レガシー — Phase 7 リポジトリに存在しないため、デフォルト path 解決が
    `[Errno 2] No such file or directory` で落ちて run-all-core の最終 step
    (`ops-accuracy-report`) が常に fail していた (Phase 7 Run 5)。
    EVAL_CASES_FILE で path 上書きは引き続き可能。
    """
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "app" / "data" / "accuracy_eval_cases.json"


def _load_cases(path: Path) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("cases must be a non-empty list")
    case_tag = os.environ.get("EVAL_CASES_TAG", "5-vertex")
    cases: list[EvalCase] = []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"case[{i}] must be an object")
        targets = row.get("targets")
        if isinstance(targets, list) and case_tag not in {str(x) for x in targets}:
            continue
        query_raw = row.get("query")
        if query_raw is None:
            query_raw = row.get("q")
        query = str(query_raw or "").strip()
        if not query:
            raise ValueError(f"case[{i}] query is required")
        relevant_raw = row.get("relevant_property_ids")
        if relevant_raw is None:
            relevant_raw = row.get("relevant_ids", [])
        if not isinstance(relevant_raw, list) or not relevant_raw:
            raise ValueError(f"case[{i}] relevant_property_ids must be a non-empty list")
        relevant_property_ids = [str(x) for x in relevant_raw]
        name = str(row.get("name") or f"case-{i}")
        filters = row.get("filters")
        if filters is None:
            filters = {}
            if row.get("layout") is not None:
                filters["layout"] = row.get("layout")
            if row.get("price_lte") is not None:
                filters["max_rent"] = int(row["price_lte"])
            if row.get("pet") is not None:
                filters["pet_ok"] = bool(row["pet"])
        if not isinstance(filters, dict):
            raise ValueError(f"case[{i}] filters must be an object")
        top_k = int(row.get("top_k", row.get("limit", 20)))
        cases.append(
            EvalCase(
                name=name,
                query=query,
                filters=filters,
                top_k=top_k,
                relevant_property_ids=relevant_property_ids,
            )
        )
    if not cases:
        raise ValueError(f"no cases matched EVAL_CASES_TAG={case_tag}")
    return cases


def _dcg_binary(relevance: list[int], *, k: int) -> float:
    score = 0.0
    for i, rel in enumerate(relevance[:k], start=1):
        if rel > 0:
            score += 1.0 / math.log2(i + 1.0)
    return score


def _ndcg_at_k_binary(relevance: list[int], *, k: int) -> float:
    actual = _dcg_binary(relevance, k=k)
    ideal = _dcg_binary(sorted(relevance, reverse=True), k=k)
    if ideal == 0.0:
        return 0.0
    return actual / ideal


def _hit_rate_at_k_binary(relevance: list[int], *, k: int) -> float:
    return 1.0 if any(r > 0 for r in relevance[:k]) else 0.0


def _mrr_at_k_binary(relevance: list[int], *, k: int) -> float:
    for i, rel in enumerate(relevance[:k], start=1):
        if rel > 0:
            return 1.0 / float(i)
    return 0.0


def main() -> int:
    cases_file = Path(os.environ.get("EVAL_CASES_FILE", str(_default_cases_path())))
    k = int(os.environ.get("EVAL_K", "10"))
    min_hit_rate = float(os.environ.get("MIN_HIT_RATE_AT_K", "0.0001"))
    if k <= 0:
        return fail("EVAL_K must be > 0")
    try:
        cases = _load_cases(cases_file)
        resolved = resolve_api_target()
    except Exception as exc:
        return fail(f"accuracy-report config error: {exc}")
    api_url = resolved.url

    per_case: list[dict] = []
    ndcgs: list[float] = []
    hit_rates: list[float] = []
    mrrs: list[float] = []

    for case in cases:
        payload = {"query": case.query, "filters": case.filters, "top_k": case.top_k}
        status, body = resolved.call("POST", "/search", payload=payload)
        if status != 200:
            return fail(f"accuracy-report search failed ({case.name}) HTTP {status}: {body}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return fail(f"accuracy-report search returned non-JSON ({case.name}): {body}")
        rows = data.get("results", [])
        if not isinstance(rows, list):
            return fail(f"accuracy-report malformed results ({case.name})")
        relevant_set = set(case.relevant_property_ids)
        relevance: list[int] = []
        matched: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("property_id", ""))
            hit = 1 if pid in relevant_set else 0
            relevance.append(hit)
            if hit:
                matched.append(pid)
        ndcg = _ndcg_at_k_binary(relevance, k=k)
        hit_rate = _hit_rate_at_k_binary(relevance, k=k)
        mrr = _mrr_at_k_binary(relevance, k=k)
        ndcgs.append(ndcg)
        hit_rates.append(hit_rate)
        mrrs.append(mrr)
        per_case.append(
            {
                "name": case.name,
                "query": case.query,
                "returned": len(rows),
                "relevant_total": len(case.relevant_property_ids),
                "matched_in_results": len(matched),
                f"ndcg_at_{k}": round(ndcg, 4),
                f"hit_rate_at_{k}": round(hit_rate, 4),
                f"mrr_at_{k}": round(mrr, 4),
            }
        )

    summary = {
        f"ndcg_at_{k}": round(sum(ndcgs) / len(ndcgs), 4),
        f"hit_rate_at_{k}": round(sum(hit_rates) / len(hit_rates), 4),
        f"mrr_at_{k}": round(sum(mrrs) / len(mrrs), 4),
    }
    report = {
        "target": resolved.mode,
        "api_url": api_url,
        "cases_file": str(cases_file),
        "num_cases": len(cases),
        "k": k,
        "summary": summary,
        "per_case": per_case,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if summary[f"hit_rate_at_{k}"] < min_hit_rate:
        return fail(
            "accuracy-report gate failed: "
            f"hit_rate_at_{k}={summary[f'hit_rate_at_{k}']} < MIN_HIT_RATE_AT_K={min_hit_rate}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
