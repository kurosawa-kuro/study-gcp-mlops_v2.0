"""Pin the top-level routing contract for ``create_app``.

The Phase 7 reorg split overloaded paths so external systems (Prometheus
GMP / SLO scrape) and the operator UI don't fight for the same URLs.
This test fixes the surface so a future refactor can't silently
regress it:

- ``GET /`` → 308 redirect to ``/ui/``
- ``GET /ui/`` → HTML (end-user search UI)
- ``GET /ui/dev`` → HTML (developer search UI)
- ``GET /ui/dev/model/metrics`` → HTML (accuracy dashboard)
- ``GET /ui/dev/data`` → HTML (model info viewer)
- ``GET /ui/dev/ops`` → HTML (destroy-all residual checker)
- ``GET /metrics`` → text/plain Prometheus exposition (NOT HTML)
- ``GET /livez`` / ``/healthz`` / ``/readyz`` reachable

Routes are checked without booting the lifespan (no GCP creds), so
container-dependent endpoints (``/search`` etc.) are NOT exercised here —
those have their own tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_no_lifespan(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Create the real app but skip the lifespan / ContainerBuilder.

    Patches ``app.main.ContainerBuilder`` so importing the app + going
    through TestClient context doesn't try to instantiate GCP clients.
    """
    from app import main
    from app.composition_root import ContainerBuilder

    real_init = ContainerBuilder.__init__

    class _NoopContainer:
        pass

    def _build(self):  # type: ignore[no-untyped-def]
        return _NoopContainer()

    monkeypatch.setattr(
        ContainerBuilder,
        "__init__",
        lambda self, settings, **kwargs: real_init(self, settings, **kwargs),
    )
    monkeypatch.setattr(ContainerBuilder, "build", _build)
    return main.create_app()


def test_root_redirects_to_ui(app_no_lifespan) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app_no_lifespan) as client:
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 308
        assert r.headers["location"] == "/ui/"


def test_ui_home_returns_html(app_no_lifespan) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app_no_lifespan) as client:
        r = client.get("/ui/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "一般向け検索" in r.text


def test_ui_dev_returns_html(app_no_lifespan) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app_no_lifespan) as client:
        r = client.get("/ui/dev")
        assert r.status_code == 200
        assert "開発者検索" in r.text


def test_ui_model_metrics_returns_html(app_no_lifespan) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app_no_lifespan) as client:
        r = client.get("/ui/dev/model/metrics")
        assert r.status_code == 200
        assert "モデル精度" in r.text


def test_ui_data_returns_html(app_no_lifespan) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app_no_lifespan) as client:
        r = client.get("/ui/dev/data")
        assert r.status_code == 200
        assert "学習データ" in r.text


def test_ui_ops_returns_html(app_no_lifespan) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app_no_lifespan) as client:
        r = client.get("/ui/dev/ops")
        assert r.status_code == 200
        assert "運用チェック" in r.text


def test_metrics_serves_prometheus_exposition(app_no_lifespan) -> None:  # type: ignore[no-untyped-def]
    """``/metrics`` must NOT be HTML (was the Phase 5 inheritance bug).

    Prometheus exposition uses ``text/plain; version=0.0.4`` content type
    and `# HELP` / `# TYPE` comments. The bug returned ``text/html`` from
    a Jinja template; this test prevents recurrence.
    """
    with TestClient(app_no_lifespan) as client:
        # Hit a real route first so the instrumentator records a series.
        client.get("/livez")
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "text/html" not in r.headers["content-type"]
        # Prom exposition has `# HELP` lines for every registered metric.
        assert "# HELP" in r.text


def test_metrics_emits_slo_compatible_labels(app_no_lifespan) -> None:  # type: ignore[no-untyped-def]
    """Pin the label contract the GCP SLO module depends on.

    ``infra/terraform/modules/slo/main.tf`` filters by
    ``metric.label."service"="search-api"`` and
    ``metric.label."status"=monitoring.regex.full_match("2..")``. If the
    instrumentor stops emitting these labels the SLO scrape selects zero
    series and Terraform apply fails — the same regression that blocked
    Phase 7 Run 1. This test catches it before deploy.
    """
    with TestClient(app_no_lifespan) as client:
        # /docs is NOT in the excluded_handlers list so it produces a 2xx
        # http_requests_total series we can match against the SLO filter.
        client.get("/docs")
        body = client.get("/metrics").text
    samples = [line for line in body.splitlines() if line.startswith("http_requests_total{")]
    assert any('service="search-api"' in s and 'status="2xx"' in s for s in samples), (
        f"no SLO-compatible series found; samples={samples!r}"
    )


def test_livez_unconditional(app_no_lifespan) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app_no_lifespan) as client:
        assert client.get("/livez").status_code == 200
        assert client.get("/healthz").status_code == 200
