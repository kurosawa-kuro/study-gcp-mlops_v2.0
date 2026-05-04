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
    # Phase 3: observability / OTEL は使わない。Phase 7 では service_name を返していた。
    return JSONResponse(
        {
            "status": "ready",
            "search_enabled": True,
            "rerank_enabled": container.reranker_client is not None,
            "model_path": container.model_path,
        }
    )


@router.get("/health")
def health() -> dict[str, str]:
    """Phase 3 用 /health (Phase 7 は /livez を採用)。Makefile / docker healthcheck から叩く。"""
    return {"status": "ok"}
