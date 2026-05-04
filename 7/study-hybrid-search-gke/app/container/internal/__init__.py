"""Internal helpers for ``app.container`` builders.

Anything imported only by ``app/container/{infra,search,ml}.py`` (i.e.
not part of the public DI surface) lives here. Mirrors the
``app/services/adapters/internal/`` convention so package-internal
helpers don't crowd the parent dir with ``_``-prefixed files.
"""

from .optional_adapter import resolve_optional_adapter

__all__ = ["resolve_optional_adapter"]
