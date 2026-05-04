"""Phase 3 — FastAPI hybrid-search API entrypoint (Local Docker Compose 版).

Phase 7 から:
- Static / UI router / model router / ops router / retrain router を削除
- Prometheus exposition / observability.py を簡素化 (標準 logging のみ)
- KServe / Vertex / Pub/Sub / BigQuery 由来の依存を全削除

DI wiring は ``app/composition_root.py``、endpoint logic は ``app/api/routers/``、
business logic は ``app/services/``。本ファイルは HTTP server entrypoint のみ。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.middleware import RequestLoggingMiddleware
from app.api.routers import feedback_router, health_router, search_router
from app.composition_root import ContainerBuilder
from app.settings import ApiSettings
from ml.common.logging import configure_logging, get_logger


def create_app() -> FastAPI:
    configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))
    settings = ApiSettings()
    logger = get_logger("app")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Build the immutable Container once and stash on app state."""
        configure_logging(level=settings.log_level)
        app.state.container = ContainerBuilder(settings).build()
        yield

    app = FastAPI(
        title="Phase 3: Local hybrid-search API (Meilisearch + ME5 + pgvector + LightGBM)",
        lifespan=lifespan,
    )
    app.add_middleware(RequestLoggingMiddleware, logger=logger)

    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(feedback_router)

    return app


app = create_app()
