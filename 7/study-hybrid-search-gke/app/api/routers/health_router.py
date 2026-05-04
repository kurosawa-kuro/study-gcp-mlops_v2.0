"""``/livez`` ``/healthz`` ``/readyz`` endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import get_container
from app.composition_root import Container

router = APIRouter()


@router.get("/livez")
@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(container: Annotated[Container, Depends(get_container)]) -> JSONResponse:
    if container.candidate_retriever is None or container.encoder_client is None:
        return JSONResponse({"status": "loading"}, status_code=503)
    return JSONResponse(
        {
            "status": "ready",
            # Pin the SLO ``service`` label value so on-call can confirm which
            # OTEL_SERVICE_NAME is in effect without scraping /metrics. Real
            # consumer of ``Container.observability`` — keeps the DI seam alive.
            "service": container.observability.service_name,
            "search_enabled": True,
            "rerank_enabled": container.reranker_client is not None,
            "model_path": container.model_path,
        }
    )
