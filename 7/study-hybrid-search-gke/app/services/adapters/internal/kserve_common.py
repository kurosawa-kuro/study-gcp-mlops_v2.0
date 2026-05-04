"""Shared helpers for the KServe encoder / reranker adapters.

Phase B-2 split ``kserve_prediction.py`` (623 lines) into separate
``kserve_encoder.py`` / ``kserve_reranker.py`` modules. These helpers
were previously top-level in the combined file.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("app.kserve_prediction")

# Expected embedding dim for multilingual-e5-base. The Phase 7 BQ
# VECTOR_SEARCH index is created with this exact dim (see
# docs/runbook/05_運用.md STEP 16); a mismatch here means BQ semantic search will
# fail later in the /search pipeline with an opaque "vector dimension mismatch"
# error. Guard at encoder.embed time so the root cause is visible.
EXPECTED_EMBEDDING_DIM = 768
HTTP_BODY_PREVIEW_CHARS = 500


def safe_json(response: httpx.Response, *, where: str) -> Any:
    """Parse response body as JSON with a structured error log on failure.

    Envoy / Istio / Gateway often serve HTML 502 / 503 pages when a KServe Pod
    is CrashLoopBackOff or unresponsive. ``response.json()`` on those bodies
    raises ``json.JSONDecodeError`` — a subclass of ``ValueError`` that is NOT
    caught by ``except httpx.HTTPError``. Wrap it here so Phase 7 operators
    see "KServe returned non-JSON body" with the HTML preview instead of a
    cryptic ValueError traceback.
    """
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        body_preview = response.text[:HTTP_BODY_PREVIEW_CHARS] if response.text else ""
        content_type = response.headers.get("content-type", "")
        logger.error(
            "%s NON_JSON_RESPONSE status=%d content_type=%r body[:%d]=%r exc=%s",
            where,
            response.status_code,
            content_type,
            HTTP_BODY_PREVIEW_CHARS,
            body_preview,
            str(exc),
        )
        raise RuntimeError(
            f"KServe {where} returned non-JSON response "
            f"(status={response.status_code}, content_type={content_type!r}). "
            f"body preview: {body_preview!r}. Likely: KServe Pod CrashLoop or "
            f"Envoy/Istio emitting an HTML error page. "
            f"Check `kubectl -n kserve-inference get pods` and `kubectl logs`."
        ) from exc


def log_http_error_response(
    response: httpx.Response,
    *,
    where: str,
    endpoint: str,
    elapsed_ms: float,
    details: str = "",
) -> None:
    """Emit a consistent preview log before ``raise_for_status``.

    The adapters deliberately log the body preview first so upstream 4xx/5xx
    failures remain triageable even when ``httpx`` raises a generic
    ``HTTPStatusError``.
    """
    body_preview = response.text[:HTTP_BODY_PREVIEW_CHARS]
    suffix = f" {details}" if details else ""
    logger.error(
        "%s HTTP %d endpoint=%s elapsed_ms=%.0f body[:%d]=%r%s",
        where,
        response.status_code,
        endpoint,
        elapsed_ms,
        HTTP_BODY_PREVIEW_CHARS,
        body_preview,
        suffix,
    )


def is_v2_inference_url(url: str) -> bool:
    return "/v2/models/" in url


def coerce_float_list(value: Any, *, field_name: str) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value]
    raise TypeError(f"Expected list for {field_name}, got {type(value).__name__}")


def response_summary(response_json: Any) -> str:
    """Short text summary for logs (never dump whole body — may be huge embedding)."""
    if isinstance(response_json, dict):
        keys = sorted(response_json.keys())
        preds = response_json.get("predictions")
        outputs = response_json.get("outputs")
        n_preds = len(preds) if isinstance(preds, list) else "N/A"
        n_outputs = len(outputs) if isinstance(outputs, list) else "N/A"
        return f"dict keys={keys} predictions.len={n_preds} outputs.len={n_outputs}"
    return f"{type(response_json).__name__}"


def extract_predictions(response_json: dict[str, Any]) -> list[Any]:
    """Extract predictions from a KServe v1/v2 response.

    KServe v1 Protocol: ``{"predictions": [...]}``
    KServe v2 Protocol (Open Inference): ``{"outputs": [{"data": [...], ...}, ...]}``
    """
    if "predictions" in response_json:
        preds = list(response_json["predictions"])
        logger.info("kserve.response protocol=v1 predictions.len=%d", len(preds))
        return preds
    if "outputs" in response_json:
        outputs = response_json["outputs"]
        if not outputs:
            logger.warning("kserve.response protocol=v2 outputs=[] (empty body)")
            return []
        first = outputs[0]
        if isinstance(first, dict) and "data" in first:
            data = first["data"]
            if isinstance(data, list):
                logger.info(
                    "kserve.response protocol=v2 outputs[0].name=%s data.len=%d",
                    first.get("name", "?"),
                    len(data),
                )
                return data
    logger.error(
        "kserve.response shape UNKNOWN — cannot extract predictions. summary=%s",
        response_summary(response_json),
    )
    raise KeyError("KServe response missing 'predictions' (v1) or 'outputs' (v2)")
