"""Optional-adapter guard helper (Phase 7 Run 3、残作業 #2).

禁止技術削除後も、``if not enabled: return None`` →
``try construct: ... except: log + return None`` という同形の guard が
``MlBuilder`` 系列に残っているため、その重複をひとまとめにする helper。

対象 (採用):
- ``MlBuilder.build_popularity_scorer``
- 将来追加される opt-in adapter

対象外 (採用見送り):
- ``SearchBuilder.build_encoder_client`` / ``build_reranker_client`` は
  tuple 返却 + URL 空文字 warn の追加分岐があり、helper に押し込むと逆に
  読みにくくなるので原形を維持する
"""

from __future__ import annotations

import logging
from collections.abc import Callable


def resolve_optional_adapter[T](
    *,
    name: str,
    enabled: bool,
    factory: Callable[[], T],
    logger: logging.Logger,
) -> T | None:
    """Build ``factory()`` only when ``enabled``; swallow + log failures.

    Returns ``None`` in two cases:

    1. ``enabled`` is False — the feature flag is off intentionally
    2. ``factory()`` raises — the failure is logged via
       ``logger.exception("Failed to initialize %s", name)`` so the
       offending adapter is identifiable without having to re-grep

    The Container is allowed to start with optional adapters set to
    ``None``; handlers branch on ``container.xxx is None`` to surface 503
    for those endpoints.
    """
    if not enabled:
        return None
    try:
        return factory()
    except Exception:
        logger.exception("Failed to initialize %s", name)
        return None
