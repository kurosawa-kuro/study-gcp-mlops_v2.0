"""HTTP routers — Phase 3 では search / feedback / health + Browser UI の 4 router。

Phase 7 にあった model_router / ops_router / retrain_router は削除
(retrain / ops / model UI は Phase 4 以降の責務)。
ui_router は Phase 7 流用 (Pico-admin dark theme) で search-user 1 page のみ。
``app/main.py`` から ``build_ui_router(app_root=...)`` で組み立てて register。
"""

from .feedback_router import router as feedback_router
from .health_router import router as health_router
from .search_router import router as search_router
from .ui_router import build_ui_router

__all__ = [
    "build_ui_router",
    "feedback_router",
    "health_router",
    "search_router",
]
