"""FastAPI 推論エンドポイント."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.predict import router as predict_router
from app.config import Settings
from common.logging import get_logger
from ml.container import build_container
from ml.data.schema import FEATURE_COLS, TARGET_COL

logger = get_logger(__name__)

# フロントエンド用デフォルト値
_DEFAULTS = {
    "MedInc": 8.3, "HouseAge": 41, "AveRooms": 6.9, "AveBedrms": 1.0,
    "Population": 322, "AveOccup": 2.5, "Latitude": 37.88, "Longitude": -122.23,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build container and warm up predictor."""
    settings = Settings()
    container = build_container(settings)
    app.state.container = container
    try:
        container.predictor.warmup()
        logger.info("Predictor warmed up with latest model")
    except Exception as e:
        logger.warning("Predictor warmup skipped at startup: %s", e)
    yield


app = FastAPI(lifespan=lifespan)
_api_root = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(_api_root / "static")), name="static")
templates = Jinja2Templates(directory=str(_api_root / "templates"))
app.include_router(predict_router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"feature_cols": FEATURE_COLS, "defaults": _DEFAULTS, "active": "predict"},
    )


@app.get("/metrics", response_class=HTMLResponse)
def metrics_page(request: Request):
    settings = Settings()
    metrics_path = Path(settings.model_path).parent / "metrics.json"
    try:
        metrics = json.loads(metrics_path.read_text())
    except FileNotFoundError:
        metrics = None
    return templates.TemplateResponse(
        request, "metrics.html", {"metrics": metrics, "active": "metrics"}
    )


@app.get("/data", response_class=HTMLResponse)
def data_page(request: Request, split: str = "train", limit: int = 50):
    split = split if split in ("train", "test") else "train"
    limit = max(1, min(limit, 500))
    try:
        container = request.app.state.container
        df = container.dataset.load(split)
        total = len(df)
        sample = df.head(limit)
        columns = list(sample.columns)
        rows = sample.to_dict(orient="records")
    except Exception as e:
        logger.warning("Failed to load data: %s", e)
        columns, rows, total = [], [], 0
    return templates.TemplateResponse(
        request,
        "data.html",
        {
            "active": "data",
            "split": split,
            "limit": limit,
            "total": total,
            "columns": columns,
            "rows": rows,
            "target": TARGET_COL,
        },
    )
