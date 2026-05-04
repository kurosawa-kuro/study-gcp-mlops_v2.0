"""FastAPI ``Depends`` resolvers for the hybrid-search API.

Phase A-2 replaced the ``request.app.state.<attribute>`` ``getattr`` pattern
with explicit ``Depends`` injection. Routers in ``app/api/routers/`` now
accept their collaborators by parameter, with type-safe resolution via
``get_container`` (the Container is built once at startup by
``ContainerBuilder``; see ``app/composition_root.py``).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.composition_root import Container
from app.services.feedback_service import FeedbackService
from app.services.search_service import SearchService


def get_container(request: Request) -> Container:
    """Pull the immutable ``Container`` placed on ``app.state`` by ``lifespan``."""
    container = getattr(request.app.state, "container", None)
    if container is None:  # pragma: no cover — only hits if lifespan failed
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Composition root not initialized",
        )
    assert isinstance(container, Container)
    return container


def get_search_service(
    container: Annotated[Container, Depends(get_container)],
) -> SearchService:
    return container.search_service


def get_feedback_service(
    container: Annotated[Container, Depends(get_container)],
) -> FeedbackService:
    return container.feedback_service


def get_request_id(request: Request) -> str:
    """Reuse the request id assigned by ``RequestLoggingMiddleware``.

    Falls back to a fresh ``uuid.uuid4().hex`` when the middleware is not
    in the chain (only happens in unit tests that bypass the app stack).
    """
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return uuid.uuid4().hex
