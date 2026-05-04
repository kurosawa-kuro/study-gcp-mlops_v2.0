"""``POST /jobs/check-retrain`` — evaluate retrain conditions, publish trigger.

Phase 7 W2-4 Stage 3 (2026-05-02) で **本線スケジューラから格下げ**。本線
retrain schedule は Cloud Composer `retrain_orchestration` DAG (canonical = docs/
architecture/01_仕様と設計.md §3 / §3.6)。本 endpoint は:

- Composer DAG `retrain_orchestration::check_retrain` task が呼ぶ smoke 経路
- Cloud Scheduler `check-retrain-daily` が月 1 回叩く軽量代替 smoke (比較教材)
- 手動 manual trigger / debugging

として残置。本線スケジューラとして使用 (定期 cron) はしないこと (= §3.6 カニバリ NG)。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import get_container
from app.composition_root import Container
from app.services.retrain_policy import evaluate as evaluate_retrain
from ml.common.logging import get_logger

router = APIRouter()


@router.post("/jobs/check-retrain")
def check_retrain(
    container: Annotated[Container, Depends(get_container)],
) -> JSONResponse:
    decision = evaluate_retrain(container.retrain_queries)
    response: dict[str, object] = {
        "should_retrain": decision.should_retrain,
        "reasons": decision.reasons,
        "feedback_rows_since_last": decision.feedback_rows_since_last,
        "ndcg_current": decision.ndcg_current,
        "ndcg_week_ago": decision.ndcg_week_ago,
        "last_run_finished_at": (
            decision.last_run_finished_at.isoformat() if decision.last_run_finished_at else None
        ),
    }
    if decision.should_retrain and container.retrain_trigger_publisher is not None:
        try:
            container.retrain_trigger_publisher.publish({"reasons": decision.reasons})
            response["published"] = True
        except Exception:
            get_logger("app").exception("Failed to publish retrain-trigger")
            response["published"] = False
    return JSONResponse(response)
