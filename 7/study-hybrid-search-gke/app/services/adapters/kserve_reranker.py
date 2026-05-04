"""``RerankerClient`` adapter — KServe InferenceService for the LightGBM reranker.

Supports both plain scoring (``predict``) and scoring with per-instance
TreeSHAP attributions (``predict_with_explain``, Phase 6 T4). Two transport
shapes are accepted:

* v1 (Vertex CPR custom container, used by ``ml/serving/reranker.py``)
  — ``/v1/models/<name>:predict`` with ``{"instances": [...]}``.
* v2 (KServe MLServer LightGBM stock runtime) — ``/v2/models/<name>/infer``
  with the v2 ``inputs`` envelope. Triggered automatically when the URL
  contains ``/v2/models/`` (動作検証結果.md Phase 7 Run 1 B18).

Explain dispatch:
* ``explain_url`` set → POST to that URL with
  ``{"instances", "feature_names"}`` (Phase 6 dedicated /explain route),
  then a separate ``predict`` call to fetch scores.
* otherwise → POST to ``endpoint_url`` with ``parameters.explain=true``
  and ``feature_names``; both predictions and attributions come back in
  one response.
"""

from __future__ import annotations

import time
import traceback
from typing import Any

import httpx

from app.services.adapters.internal.kserve_common import (
    extract_predictions,
    is_v2_inference_url,
    log_http_error_response,
    logger,
    response_summary,
    safe_json,
)


def _extract_attributions(
    response_json: dict[str, Any],
    n_instances: int,
) -> list[dict[str, float]] | None:
    """Parse per-instance attribution dicts from a reranker response.

    Supported response shapes (in priority order):
      1. Phase 6 Vertex CPR server — ``{"predictions": [...], "attributions": [...]}``
         or ``{"attributions": [...]}`` (from dedicated ``/explain`` route).
      2. KServe v2 — ``{"outputs": [..., {"name": "attributions", "data": [...]}]}``.

    Returns ``None`` when the response carries no attribution payload (e.g. the
    operator is still running the MLServer LightGBM runtime, which ignores
    ``parameters.explain=true``). Caller can treat ``None`` as "explain not
    supported by the deployed container — see docs/tasks/TASKS_ROADMAP.md §4.2 T4".

    Count-mismatch distinction: when an attribution list IS present but its
    length doesn't match ``n_instances``, this is NOT the same degraded path
    as "runtime ignored the explain param". Log LOUDLY so operators don't
    silently lose attributions due to an off-by-one container bug.
    """
    attrs = response_json.get("attributions")
    if isinstance(attrs, list):
        if len(attrs) != n_instances:
            logger.error(
                "reranker.explain COUNT_MISMATCH attributions.len=%d != n_instances=%d. "
                "Response had attribution payload but the row count disagrees with the "
                "request batch. This is a reranker-server bug, NOT a missing-runtime "
                "fallback. Dropping attributions to preserve /search response; fix the "
                "container.",
                len(attrs),
                n_instances,
            )
        else:
            return [
                {str(k): float(v) for k, v in row.items()} for row in attrs if isinstance(row, dict)
            ] or None
    outputs = response_json.get("outputs")
    if isinstance(outputs, list):
        for out in outputs:
            if isinstance(out, dict) and out.get("name") == "attributions":
                data = out.get("data")
                if isinstance(data, list):
                    if len(data) != n_instances:
                        logger.error(
                            "reranker.explain V2_COUNT_MISMATCH "
                            "outputs[attributions].data.len=%d != n_instances=%d",
                            len(data),
                            n_instances,
                        )
                    else:
                        return [
                            {str(k): float(v) for k, v in row.items()}
                            for row in data
                            if isinstance(row, dict)
                        ] or None
    return None


class KServeReranker:
    """Adapter over a KServe InferenceService that returns one score per row.

    Operators that deploy a dedicated ``/explain`` route (separate URL) can
    pass ``explain_url`` at construction time; the adapter will prefer that
    URL when attributions are requested.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        explain_url: str | None = None,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url.strip()
        if not self.endpoint_url:
            raise ValueError("KServeReranker requires a non-empty endpoint_url")
        self.endpoint_name = self.endpoint_url
        self.model_path = self.endpoint_url
        # Treat whitespace-only strings as "no explain URL configured" so
        # misconfigured ConfigMap values (accidental trailing newline / tab)
        # degrade to the parameters.explain=true fallback instead of producing
        # a bogus request to an empty URL.
        _explain = explain_url.strip() if explain_url else ""
        self.explain_url = _explain if _explain else None
        self._timeout_seconds = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)
        logger.info(
            "KServeReranker init endpoint_url=%s explain_url=%s timeout=%.1fs (expect "
            "path `/v1/models/property-reranker:predict` for MLServer LightGBM runtime; "
            "explain requires Vertex CPR container or equivalent)",
            self.endpoint_url,
            self.explain_url or "(fallback: parameters.explain=true on predict URL)",
            timeout_seconds,
        )

    def predict(self, instances: list[list[float]]) -> list[float]:
        if not instances:
            logger.warning("reranker.predict called with empty instances")
            return []
        # endpoint URL のパターンで protocol を切り替える:
        # - ``/v2/models/<name>/infer`` → KServe MLServer LightGBM stock runtime (v2)
        # - ``/v1/models/<name>:predict`` → Vertex CPR custom container (v1)。
        #   Phase 7 では `property-reranker-explain` Pod (TreeSHAP 付き) が v1 を
        #   採用しているので、v1 path は active な分岐 (legacy ではない)。
        is_v2 = is_v2_inference_url(self.endpoint_url)
        if is_v2:
            n_rows = len(instances)
            n_cols = len(instances[0]) if instances else 0
            flat = [float(v) for row in instances for v in row]
            payload: dict[str, Any] = {
                "inputs": [
                    {
                        "name": "input-0",
                        "shape": [n_rows, n_cols],
                        "datatype": "FP64",
                        "data": flat,
                    }
                ]
            }
        else:
            payload = {"instances": instances}
        logger.info(
            "reranker.predict START endpoint=%s protocol=%s batch=%d dims=%d",
            self.endpoint_url,
            "v2" if is_v2 else "v1",
            len(instances),
            len(instances[0]) if instances else -1,
        )
        start = time.monotonic()
        try:
            response = self._client.post(self.endpoint_url, json=payload)
        except httpx.HTTPError as exc:
            logger.exception(
                "reranker.predict HTTPError endpoint=%s batch=%d exc_type=%s msg=%s\n%s",
                self.endpoint_url,
                len(instances),
                type(exc).__name__,
                str(exc),
                traceback.format_exc(),
            )
            raise
        elapsed_ms = (time.monotonic() - start) * 1000
        if response.status_code >= 400:
            log_http_error_response(
                response,
                where=f"reranker.predict batch={len(instances)}",
                endpoint=self.endpoint_url,
                elapsed_ms=elapsed_ms,
                details=f"head_instance={instances[0][:5] if instances and instances[0] else []}",
            )
        response.raise_for_status()
        response_json = safe_json(response, where="reranker.predict")
        predictions = extract_predictions(response_json)
        if len(predictions) != len(instances):
            # Length mismatch would IndexError in ranking.py when zipping
            # scores[] with candidates[]. Log the shape delta + response
            # summary so operators can diff against the known reranker
            # contract (LightGBM LambdaRank → one score per instance).
            logger.error(
                "reranker.predict SCORE_COUNT_MISMATCH endpoint=%s predictions.len=%d "
                "instances.len=%d summary=%s — ranker contract violated (expected one "
                "score per instance). Upstream will IndexError on scores[i] in ranking.py.",
                self.endpoint_url,
                len(predictions),
                len(instances),
                response_summary(response_json),
            )
            raise ValueError(
                f"KServe reranker returned {len(predictions)} scores for "
                f"{len(instances)} instances (expected equal)"
            )
        scores = [
            self._coerce_score(prediction, idx=idx) for idx, prediction in enumerate(predictions)
        ]
        logger.info(
            "reranker.predict OK endpoint=%s batch=%d scores=%d elapsed_ms=%.0f "
            "score_range=[%.4f, %.4f]",
            self.endpoint_url,
            len(instances),
            len(scores),
            elapsed_ms,
            min(scores) if scores else 0.0,
            max(scores) if scores else 0.0,
        )
        return scores

    def predict_with_explain(
        self,
        instances: list[list[float]],
        feature_names: list[str],
    ) -> tuple[list[float], list[dict[str, float]]]:
        """Score + TreeSHAP attribution in a single round-trip.

        Dispatches via ``explain_url`` (dedicated ``/explain`` route) when the
        adapter was constructed with one, otherwise POSTs to ``endpoint_url``
        with ``parameters.explain=true`` + ``feature_names`` (matching the
        Phase 6 Vertex CPR reranker contract in ``ml/serving/reranker.py``).

        Degradation policy: if the deployed container silently ignores the
        explain parameter and returns only scores, we emit a warning and
        return empty ``{}`` attribution dicts for every instance. The caller
        (``app.services.ranking``) surfaces these as ``attributions=None``
        per row, so the ``/search?explain=true`` response stays 200 with
        attributions missing rather than 500-ing on the client.
        """
        if not instances:
            logger.warning("reranker.predict_with_explain called with empty instances")
            return [], []
        url = self.explain_url or self.endpoint_url
        use_explain_route = self.explain_url is not None
        # KServe MLServer (LightGBM stock runtime) は v2 protocol のみで、
        # TreeSHAP attribution を返すフックは持たない (B19 Phase 7 Run 2
        # 検証で /v2/models/<name>/infer に v1 explain payload を送ると
        # 422 Unprocessable Entity になることを確認済)。endpoint URL に
        # ``/v2/models/`` が含まれる場合は v2 払い + 空 attributions に
        # degrade して /search?explain=true を 200 で返し、運用者には
        # warn ログで「container を Vertex CPR に切り替えれば SHAP が出る」
        # ことを案内する (B18 と同パターン)。
        is_v2 = is_v2_inference_url(url)
        if is_v2 and not use_explain_route:
            scores = self.predict(instances)
            logger.warning(
                "reranker.predict_with_explain url=%s batch=%d: KServe MLServer v2 "
                "stock runtime does not support attributions — returning empty dicts. "
                "Wire `explain_url` to a Vertex CPR `/explain` route to get TreeSHAP.",
                url,
                len(instances),
            )
            return scores, [{} for _ in instances]
        if use_explain_route:
            # Dedicated /explain route (Phase 6 Vertex CPR custom server): body
            # is {instances, feature_names}, response is {attributions}. We
            # still need scores, so issue a separate predict call afterwards
            # when attributions come back.
            payload: dict[str, Any] = {"instances": instances, "feature_names": feature_names}
        else:
            # /predict with explain param: single round-trip, response carries
            # both predictions and attributions.
            payload = {
                "instances": instances,
                "parameters": {"explain": True, "feature_names": feature_names},
            }
        logger.info(
            "reranker.predict_with_explain START url=%s batch=%d use_explain_route=%s",
            url,
            len(instances),
            use_explain_route,
        )
        start = time.monotonic()
        try:
            response = self._client.post(url, json=payload)
        except httpx.HTTPError as exc:
            logger.exception(
                "reranker.predict_with_explain HTTPError url=%s batch=%d exc_type=%s msg=%s\n%s",
                url,
                len(instances),
                type(exc).__name__,
                str(exc),
                traceback.format_exc(),
            )
            raise
        elapsed_ms = (time.monotonic() - start) * 1000
        if response.status_code >= 400:
            log_http_error_response(
                response,
                where=f"reranker.predict_with_explain batch={len(instances)}",
                endpoint=url,
                elapsed_ms=elapsed_ms,
            )
        response.raise_for_status()
        response_json = safe_json(response, where="reranker.predict_with_explain")
        attributions = _extract_attributions(response_json, len(instances))
        if use_explain_route:
            # /explain gave us only attributions; fetch scores with a regular
            # predict call. Cheap because it runs against the same booster.
            scores = self.predict(instances)
        else:
            try:
                predictions = extract_predictions(response_json)
            except KeyError:
                logger.error(
                    "reranker.predict_with_explain response missing predictions. summary=%s",
                    response_summary(response_json),
                )
                raise
            scores = [
                self._coerce_score(prediction, idx=idx)
                for idx, prediction in enumerate(predictions)
            ]
        if attributions is None:
            logger.warning(
                "reranker.predict_with_explain url=%s batch=%d: response carries no "
                "attribution payload — deployed container likely ignores explain. "
                "Returning empty dicts. Switch reranker container to the Phase 6 Vertex "
                "CPR image (ml/serving/reranker.py) or wire `explain_url` to a route "
                "that returns {attributions}. summary=%s",
                url,
                len(instances),
                response_summary(response_json),
            )
            attributions = [{} for _ in instances]
        logger.info(
            "reranker.predict_with_explain OK url=%s batch=%d scores=%d attrs=%d elapsed_ms=%.0f",
            url,
            len(instances),
            len(scores),
            len(attributions),
            elapsed_ms,
        )
        return scores, attributions

    @staticmethod
    def _coerce_score(prediction: Any, *, idx: int) -> float:
        if isinstance(prediction, dict):
            for key in ("score", "prediction", "value"):
                if key in prediction:
                    return float(prediction[key])
            logger.error(
                "reranker response[%d] dict missing score payload. "
                "available_keys=%s (expected one of: score / prediction / value)",
                idx,
                sorted(prediction.keys()),
            )
            raise KeyError("KServe reranker response dict missing score payload")
        return float(prediction)
