"""``EncoderClient`` adapter — KServe InferenceService for multilingual-e5.

Cluster-local HTTP (NetworkPolicy restricts callers to the search-api Pod).
Authentication is not required at the HTTP layer.

Phase 7 Run 2 で encoder runtime を KServe HuggingFace stock runtime
(``kserve/huggingfaceserver`` + ``intfloat/multilingual-e5-base`` /
``--task=text_embedding``) に切り替えたため、payload は HF v1 規約の
``{"instances": ["<prefix>: <text>"]}`` に統一。E5 の `query: ` /
`passage: ` prefix は本 adapter が client 側で付与する (HF stock runtime
は task 推論のみで E5 prefix を知らない)。

旧 Phase 5 Run 6 の `{"instances": [{"text": ..., "kind": ...}]}` 形式は
自前 Vertex CPR encoder server (`ml/serving/encoder.py::E5Encoder`) 用で、
HF runtime に投げると ``pd.DataFrame({"text": "scalar", "kind": "scalar"})``
が ``If using all scalar values, you must pass an index`` で 500 を返す
(infra/manifests/kserve/encoder.yaml の切替コメント参照)。
"""

from __future__ import annotations

import time
from typing import Literal

import httpx

from app.services.adapters.internal.kserve_common import (
    EXPECTED_EMBEDDING_DIM,
    coerce_float_list,
    extract_predictions,
    log_http_error_response,
    logger,
    response_summary,
    safe_json,
)


class KServeEncoder:
    """Adapter over a KServe InferenceService that returns one embedding per text."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
        expected_dim: int = EXPECTED_EMBEDDING_DIM,
    ) -> None:
        self.endpoint_url = endpoint_url.strip()
        if not self.endpoint_url:
            raise ValueError("KServeEncoder requires a non-empty endpoint_url")
        self.endpoint_name = self.endpoint_url
        self._timeout_seconds = timeout_seconds
        # ``expected_dim`` is primarily a test override; production paths
        # stick with 768 to enforce the BQ VECTOR_SEARCH contract. Set to
        # 0 to disable the strict dimension check (empty/NaN guards still apply).
        self._expected_dim = expected_dim
        self._client = client or httpx.Client(timeout=timeout_seconds)
        logger.info(
            "KServeEncoder init endpoint_url=%s timeout=%.1fs expected_dim=%d "
            "(expect path `/predict` for Vertex CPR encoder server)",
            self.endpoint_url,
            timeout_seconds,
            expected_dim,
        )

    def embed(self, text: str, kind: Literal["query", "passage"]) -> list[float]:
        text_stripped = text.strip()
        # E5 prefix は client 側で付与 (HF stock runtime は task 推論のみで
        # E5 prefix を知らない)。`{kind}: {text}` を素の文字列で送る。
        prefixed_text = f"{kind}: {text_stripped}"
        payload = {"instances": [prefixed_text]}
        logger.info(
            "encoder.embed START endpoint=%s kind=%s text_len=%d",
            self.endpoint_url,
            kind,
            len(text_stripped),
        )
        start = time.monotonic()
        try:
            response = self._client.post(self.endpoint_url, json=payload)
        except httpx.HTTPError as exc:
            logger.exception(
                "encoder.embed HTTPError endpoint=%s kind=%s exc_type=%s msg=%s",
                self.endpoint_url,
                kind,
                type(exc).__name__,
                str(exc),
            )
            raise
        elapsed_ms = (time.monotonic() - start) * 1000
        if response.status_code >= 400:
            # Phase 5 Run 6 の 422 再発を即座に検知するため status + body 先頭を dump
            log_http_error_response(
                response,
                where=f"encoder.embed kind={kind}",
                endpoint=self.endpoint_url,
                elapsed_ms=elapsed_ms,
            )
        response.raise_for_status()
        response_json = safe_json(response, where="encoder.embed")
        predictions = extract_predictions(response_json)
        if not predictions:
            logger.error(
                "encoder.embed empty predictions endpoint=%s kind=%s summary=%s",
                self.endpoint_url,
                kind,
                response_summary(response_json),
            )
            raise ValueError("KServe encoder returned no predictions")
        first = predictions[0]
        if isinstance(first, dict):
            for key in ("embedding", "embeddings", "values"):
                if key in first:
                    vec = coerce_float_list(first[key], field_name=key)
                    self._validate_embedding(
                        vec, kind=kind, via=f"dict.{key}", expected_dim=self._expected_dim
                    )
                    logger.info(
                        "encoder.embed OK endpoint=%s kind=%s dim=%d elapsed_ms=%.0f via_key=%s",
                        self.endpoint_url,
                        kind,
                        len(vec),
                        elapsed_ms,
                        key,
                    )
                    return vec
            logger.error(
                "encoder response dict missing embedding payload. "
                "available_keys=%s (expected one of: embedding / embeddings / values)",
                sorted(first.keys()),
            )
            raise KeyError("KServe encoder response dict missing embedding payload")
        vec = coerce_float_list(first, field_name="prediction")
        self._validate_embedding(vec, kind=kind, via="bare_list", expected_dim=self._expected_dim)
        logger.info(
            "encoder.embed OK endpoint=%s kind=%s dim=%d elapsed_ms=%.0f via=bare_list",
            self.endpoint_url,
            kind,
            len(vec),
            elapsed_ms,
        )
        return vec

    @staticmethod
    def _validate_embedding(vec: list[float], *, kind: str, via: str, expected_dim: int) -> None:
        """Validate an embedding vector before returning it upstream.

        Catches three silent failure modes that would otherwise surface as
        opaque errors downstream:

        1. Empty list — BQ ``VECTOR_SEARCH(..., query_vector => [], ...)``
           returns zero candidates with no error. Empty query vectors silently
           break semantic recall.
        2. Wrong dimension — the ME5-base → BQ index contract is 768d. A 512d
           vector (e.g., from a wrong Model Registry version) triggers a
           downstream "vector dimension mismatch" error that points at BQ,
           not at the encoder. ``expected_dim=0`` disables this check.
        3. NaN/inf — LightGBM downstream rejects these but the error message
           is "Invalid input data" without the actual bad row.
        """
        if not vec:
            logger.error(
                "encoder.embed EMPTY_EMBEDDING kind=%s via=%s — KServe returned a "
                "zero-length embedding. Downstream BQ VECTOR_SEARCH will silently "
                "return zero candidates. Check predictor model version.",
                kind,
                via,
            )
            raise ValueError(f"KServe encoder returned empty embedding (kind={kind})")
        if expected_dim and len(vec) != expected_dim:
            logger.error(
                "encoder.embed DIM_MISMATCH kind=%s via=%s actual_dim=%d expected_dim=%d — "
                "BQ VECTOR_SEARCH index is built for %dd vectors. Likely: wrong model "
                "checkpoint loaded (not multilingual-e5-base) or wrong Model Registry "
                "version. Check KServe InferenceService storageUri.",
                kind,
                via,
                len(vec),
                expected_dim,
                expected_dim,
            )
            raise ValueError(
                f"KServe encoder returned {len(vec)}d embedding, "
                f"expected {expected_dim}d (kind={kind})"
            )
        # Check for NaN / inf — iterate once, short-circuit on first bad value.
        for idx, value in enumerate(vec):
            if value != value:  # NaN check (NaN != NaN)
                logger.error(
                    "encoder.embed NAN_IN_EMBEDDING kind=%s via=%s dim_index=%d",
                    kind,
                    via,
                    idx,
                )
                raise ValueError(f"KServe encoder returned NaN at index {idx} (kind={kind})")
            if value == float("inf") or value == float("-inf"):
                logger.error(
                    "encoder.embed INF_IN_EMBEDDING kind=%s via=%s dim_index=%d value=%r",
                    kind,
                    via,
                    idx,
                    value,
                )
                raise ValueError(f"KServe encoder returned {value} at index {idx} (kind={kind})")
