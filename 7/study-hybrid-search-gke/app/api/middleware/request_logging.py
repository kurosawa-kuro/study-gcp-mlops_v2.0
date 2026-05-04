"""Access-log middleware — writes structured request completion logs.

Adapted from starter-kit/mlops/api/gcp.py. Uses the project-wide
CloudLoggingJsonFormatter installed by ml.common.logging.configure_logging().
"""

from __future__ import annotations

import logging
import os
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


def _extract_trace(request: Request) -> str | None:
    project = (
        os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    )
    header = request.headers.get("x-cloud-trace-context")
    if not project or not header:
        return None
    trace_id = header.split("/", 1)[0]
    if not trace_id:
        return None
    return f"projects/{project}/traces/{trace_id}"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, logger: logging.Logger) -> None:
        super().__init__(app)
        self._logger = logger

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        trace = _extract_trace(request)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._logger.exception(
                "request failed",
                extra={
                    "extras": {
                        "method": request.method,
                        "path": request.url.path,
                        "latency_ms": round(elapsed_ms, 2),
                        "request_id": request_id,
                        "logging.googleapis.com/trace": trace,
                    }
                },
            )
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = request_id
        self._logger.info(
            "request completed",
            extra={
                "extras": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": round(elapsed_ms, 2),
                    "request_id": request_id,
                    "logging.googleapis.com/trace": trace,
                }
            },
        )
        return response
