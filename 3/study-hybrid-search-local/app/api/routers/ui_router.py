"""Phase 3 — Browser UI router (Phase 7 から流用、search-user 1 page のみ).

Phase 7 の `ui_router.py` から ``ui-search-dev`` / ``ui-model-metrics`` /
``ui-data`` / ``ui-ops`` を削除した最小版。

UI ページは AJAX `fetch()` で `/search` / `/feedback` を叩く。
Jinja2 templates は `app/templates/`、static asset は `app/static/`。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates


def build_ui_router(*, app_root: Path) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory=str(app_root / "templates"))

    @router.get("/ui/", name="ui-home")
    @router.get("/ui", name="ui-home-noslash", include_in_schema=False)
    def ui_home(request: Request) -> object:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "active": "search-user",
                "page_mode": "user",
                "default_query": "新宿区西新宿 1LDK",
                "default_max_rent": 150000,
                "default_top_k": 20,
            },
        )

    @router.get("/", include_in_schema=False)
    def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/ui/", status_code=308)

    return router
