"""Vertex custom prediction routine for the LightGBM LambdaRank reranker.

Phase 6 T4 (Explainable AI): the same container answers two questions —
"what is the score?" (``/predict``, unchanged) and "why that score?"
(``/explain``, new). Both routes share the booster loaded at startup.

We implement explanations with LightGBM's built-in ``pred_contrib=True``
(TreeSHAP) rather than Vertex's framework-native ``ExplanationSpec``, so
operators do not have to wire ``ExplanationMetadata`` for a custom
container. Attributions come back keyed by the ranker feature names the
adapter passes in, matching ``FEATURE_COLS_RANKER``.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import lightgbm as lgb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ml.registry.artifact_store import download_file


class RerankerParameters(BaseModel):
    """Optional extras forwarded via Vertex ``Endpoint.predict(parameters=...)``.

    ``explain=True`` asks the container to return per-instance TreeSHAP
    attributions alongside the scalar score, keyed by ``feature_names``.
    When ``feature_names`` is shorter than the feature vector, trailing
    columns are labeled ``feature_<i>``.
    """

    explain: bool = False
    feature_names: list[str] | None = None


class RerankerRequest(BaseModel):
    instances: list[list[float]] = Field(min_length=1)
    parameters: RerankerParameters | None = None


class RerankerResponse(BaseModel):
    predictions: list[float]
    attributions: list[dict[str, float]] | None = None


class ExplainRequest(BaseModel):
    instances: list[list[float]] = Field(min_length=1)
    feature_names: list[str] | None = None


class ExplainResponse(BaseModel):
    attributions: list[dict[str, float]]


def _load_booster() -> lgb.Booster:
    local_model_path = os.getenv("LOCAL_RERANKER_MODEL_PATH", "").strip()
    if local_model_path:
        return lgb.Booster(model_file=local_model_path)
    storage_uri = os.getenv("AIP_STORAGE_URI", "").strip()
    if not storage_uri:
        raise RuntimeError("AIP_STORAGE_URI or LOCAL_RERANKER_MODEL_PATH is required")
    tmpdir = Path(tempfile.mkdtemp(prefix="reranker-model-"))
    model_path = download_file(f"{storage_uri.rstrip('/')}/model.txt", tmpdir / "model.txt")
    return lgb.Booster(model_file=str(model_path))


def _pred_contrib(
    booster: lgb.Booster,
    instances: list[list[float]],
    feature_names: list[str] | None,
) -> list[dict[str, float]]:
    """Compute TreeSHAP attributions via LightGBM ``pred_contrib=True``.

    LightGBM appends one extra column per instance (the expected / base value),
    so the returned row has length ``n_features + 1``. We expose the baseline
    under the reserved key ``_baseline`` to avoid clashing with a feature name.
    """
    contribs: Any = booster.predict(instances, pred_contrib=True)
    rows = [list(row) for row in contribs]
    attributions: list[dict[str, float]] = []
    for row in rows:
        n_features = len(row) - 1
        if feature_names and len(feature_names) == n_features:
            keyed: dict[str, float] = {name: float(row[i]) for i, name in enumerate(feature_names)}
        else:
            keyed = {f"feature_{i}": float(row[i]) for i in range(n_features)}
        keyed["_baseline"] = float(row[-1])
        attributions.append(keyed)
    return attributions


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.booster = _load_booster()
    yield


app = FastAPI(title="vertex-reranker-server", lifespan=lifespan)
app.state.booster = None


@app.get(os.getenv("AIP_HEALTH_ROUTE", "/health"))
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(os.getenv("AIP_PREDICT_ROUTE", "/predict"), response_model=RerankerResponse)
def predict(request: RerankerRequest) -> RerankerResponse:
    booster: lgb.Booster | None = app.state.booster
    if booster is None:
        raise HTTPException(status_code=503, detail="booster not loaded")
    predictions = booster.predict(request.instances)
    params = request.parameters or RerankerParameters()
    attributions: list[dict[str, float]] | None = None
    if params.explain:
        attributions = _pred_contrib(booster, request.instances, params.feature_names)
    return RerankerResponse(
        predictions=[float(value) for value in predictions],
        attributions=attributions,
    )


@app.post(os.getenv("AIP_EXPLAIN_ROUTE", "/explain"), response_model=ExplainResponse)
def explain(request: ExplainRequest) -> ExplainResponse:
    """Dedicated explain route. Kept separate from ``/predict`` so a future
    Vertex ``ExplanationSpec`` wiring can route ``:explain`` here without
    forcing every ``/predict`` caller to pay TreeSHAP cost.
    """
    booster: lgb.Booster | None = app.state.booster
    if booster is None:
        raise HTTPException(status_code=503, detail="booster not loaded")
    attributions = _pred_contrib(booster, request.instances, request.feature_names)
    return ExplainResponse(attributions=attributions)


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("AIP_HTTP_PORT", os.getenv("PORT", "8080"))),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
