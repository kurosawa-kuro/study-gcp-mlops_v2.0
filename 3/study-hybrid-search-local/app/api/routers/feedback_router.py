"""``POST /feedback`` — record click / favorite / inquiry events."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_feedback_service
from app.schemas import FeedbackRequest, FeedbackResponse
from app.services.feedback_service import FeedbackService

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
def feedback(
    req: FeedbackRequest,
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
) -> FeedbackResponse:
    accepted = service.record(
        request_id=req.request_id,
        property_id=req.property_id,
        action=req.action,
    )
    return FeedbackResponse(accepted=accepted)
