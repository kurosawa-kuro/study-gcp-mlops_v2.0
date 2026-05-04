"""Observability composition — single seam for metrics + logging (+ tracing).

Phase 7 Run 3 で 02_移行ロードマップ-Port-Adapter-DI.md の残作業 #1
(observability の Container 管理統一) を解消するために導入。

これまでの observability は 3 経路に散らばっていた:

1. Prometheus exposition (``app/main.py::_expose_prometheus``) — 関数 + module
   グローバル ``Counter`` / ``Histogram`` を直接 register
2. 構造化ログ (``ml.common.logging.get_logger``) を adapter / service が直呼び
3. request_id 発行 (``api/middleware/request_logging.py``) で middleware が
   logger を受け取る

本 module は 3 つのうち (1) と (2) を ``Observability`` に束ね、Container 経由で
配るための seam。tracing (Cloud Trace / OpenTelemetry) を入れるときは本 class
に ``tracer`` フィールドを追加するだけで済む。

設計メモ:
- ``Observability`` は frozen dataclass (Container 全体の不変性ポリシーに合わせる)
- ``service_name`` は ``OTEL_SERVICE_NAME`` env から (既定 ``search-api``)。SLO
  module (``infra/terraform/modules/slo/main.tf``) の good/total filter
  ``metric.label."service"="search-api"`` と一致させるための contract
- ``http_requests_total`` / ``http_request_duration_seconds`` の Counter /
  Histogram は module-level singleton (prometheus_client は同名の register 重複を
  禁止する仕様なので、Observability 自体は frozen でも metric 実体はモジュール
  globalで保持)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import Info as MetricInfo

from ml.common.logging import get_logger

_REQUEST_LABELS = ("service", "method", "handler", "status")
_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests served by the FastAPI app.",
    labelnames=_REQUEST_LABELS,
)
_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Latency of HTTP requests served by the FastAPI app.",
    labelnames=_REQUEST_LABELS,
)


@dataclass(frozen=True)
class Observability:
    """Container 経由で配るメトリクス + ロガーの束。

    - ``service_name``: Prometheus / SLO の ``service`` ラベル値
    - ``logger_factory``: 名前付きロガー取得 callable (既定 ``get_logger``)
    """

    service_name: str
    logger_factory: Callable[[str], logging.Logger]

    @classmethod
    def from_env(cls, *, default_service: str = "search-api") -> Observability:
        return cls(
            service_name=os.getenv("OTEL_SERVICE_NAME", default_service),
            logger_factory=get_logger,
        )

    @classmethod
    def for_test(cls, *, service_name: str = "search-api-test") -> Observability:
        """Build a test-friendly Observability without reading env.

        ``logging.getLogger`` (stdlib) is used rather than the
        project-wide ``ml.common.logging.get_logger`` so test runs do not
        depend on cloud logging configuration. Tests that need to assert
        log lines should use ``caplog`` against the returned logger.
        """
        return cls(service_name=service_name, logger_factory=logging.getLogger)

    def get_logger(self, name: str) -> logging.Logger:
        return self.logger_factory(name)

    def expose_prometheus(self, app: FastAPI) -> None:
        """``/metrics`` を SLO 互換ラベルで register する。

        ``infra/terraform/modules/slo/main.tf`` が
        ``metric.label."service"="search-api" AND status=~"2.."`` で
        scrape 対象を絞るので、その契約を満たす ``service`` ラベルを
        ここで付与する。``excluded_handlers`` は probe / metrics 自身を
        scrape 対象から外すためのもの (循環カウントの防止)。
        """
        instrumentator = Instrumentator(
            excluded_handlers=["/metrics", "/livez", "/healthz", "/readyz"],
        )
        instrumentator.add(self._build_tracker())
        instrumentator.instrument(app).expose(
            app,
            endpoint="/metrics",
            include_in_schema=False,
            should_gzip=False,
        )

    def _build_tracker(self) -> Callable[[MetricInfo], None]:
        service_name = self.service_name

        def _record(info: MetricInfo) -> None:
            handler = info.modified_handler or "unhandled"
            raw_status = (
                str(info.response.status_code)
                if info.response is not None and info.response.status_code is not None
                else "0"
            )
            status_class = (
                f"{raw_status[0]}xx" if raw_status and raw_status[0].isdigit() else "unknown"
            )
            _REQUESTS_TOTAL.labels(
                service=service_name,
                method=info.request.method,
                handler=handler,
                status=status_class,
            ).inc()
            _REQUEST_DURATION.labels(
                service=service_name,
                method=info.request.method,
                handler=handler,
                status=status_class,
            ).observe(info.modified_duration)

        return _record
