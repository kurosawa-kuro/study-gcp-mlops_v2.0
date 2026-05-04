"""HTTP routers — Phase 3 では search / feedback / health の 3 router のみ。

Phase 7 にあった model_router / ops_router / retrain_router / ui_router は削除
(retrain / ops / model UI は Phase 4 以降の責務、UI は教材スコープ外)。
"""

from .feedback_router import router as feedback_router
from .health_router import router as health_router
from .search_router import router as search_router

__all__ = [
    "feedback_router",
    "health_router",
    "search_router",
]
