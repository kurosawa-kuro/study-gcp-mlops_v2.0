"""FastAPI hybrid-search API — GKE Pod entrypoint.

This module is the **HTTP server entrypoint only**. DI wiring lives in
``app/composition_root.py``; endpoint logic lives in
``app/api/routers/``; mapping in ``app/api/mappers/``; business logic in
``app/services/``.

Route surfaces (kept disjoint to avoid cross-concern collision):

- **App API** — ``/search`` ``/feedback`` ``/jobs/check-retrain``
- **Probes** — ``/livez`` ``/healthz`` ``/readyz`` (k8s)
- **Prom exposition** — ``/metrics`` (GMP / SLO scrape target)
- **Browser UI** — ``/ui/`` ``/ui/dev`` ``/ui/dev/model/metrics`` ``/ui/dev/data``
  (``/`` redirects to ``/ui/`` so existing bookmarks still resolve)

The Pod keeps only retrieval / orchestration concerns. Query embeddings
and rerank scoring are delegated to KServe InferenceService (cluster-local
HTTP) when configured. PMLE technology integrations (BQML popularity) are
wired in as optional adapters per Phase 6 — see ``ContainerBuilder``.

Observability (logging / metrics / future tracing) is bundled in
``app.observability.Observability`` and shared between this entrypoint and
the Container — see the residual-task notes in
``docs/02_移行ロードマップ-Port-Adapter-DI.md``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.middleware import RequestLoggingMiddleware
from app.api.routers import (
    build_ui_router,
    feedback_router,
    health_router,
    model_router,
    ops_router,
    retrain_router,
    search_router,
)
from app.composition_root import ContainerBuilder
from app.observability import Observability
from app.settings import ApiSettings
from ml.common.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    settings = ApiSettings()
    observability = Observability.from_env()
    logger = observability.get_logger("app")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Build the immutable :class:`Container` once and stash on app state."""
        configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))
        app.state.container = ContainerBuilder(settings, observability=observability).build()
        yield

    app = FastAPI(title="gke+kserve-backed hybrid search API", lifespan=lifespan)

    app_root = Path(__file__).resolve().parent
    app.mount("/static", StaticFiles(directory=str(app_root / "static")), name="static")
    app.add_middleware(RequestLoggingMiddleware, logger=logger)

    # App API + probes (no path prefix — these are the public contracts).
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(feedback_router)
    app.include_router(retrain_router)
    app.include_router(model_router)
    app.include_router(ops_router)

    # Operator UI is namespaced under /ui/ so /metrics belongs to Prometheus.
    app.include_router(build_ui_router(app_root=app_root), prefix="/ui")

    @app.get("/", include_in_schema=False)
    def _root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/ui/", status_code=308)

    # Prometheus exposition at /metrics. The ``service`` label this emits
    # has to match the SLO module's good/total filter
    # (``metric.label."service"="search-api"`` and ``status=~"2.."``);
    # ``Observability.expose_prometheus`` owns that contract.
    observability.expose_prometheus(app)

    return app


app = create_app()
