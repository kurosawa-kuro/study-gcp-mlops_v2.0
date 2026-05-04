from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import ops_router
from scripts.ops.destroy_check import Finding

ops_router_module = importlib.import_module("app.api.routers.ops_router")


def test_destroy_check_returns_summary(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        ops_router_module,
        "collect_findings",
        lambda project_id, region, vertex_location: [
            Finding(label="GKE clusters", severity="OK", items=()),
            Finding(
                label="Managed residual buckets", severity="WARN", items=("mlops-dev-a-tfstate",)
            ),
            Finding(label="Cloud Run services", severity="FAIL", items=("meili-search",)),
        ],
    )
    app = FastAPI()
    app.include_router(ops_router)
    client = TestClient(app)

    res = client.get("/ops/destroy-check")

    assert res.status_code == 200
    body = res.json()
    assert body["project_id"] == "mlops-dev-a"
    assert body["summary"] == {"ok": 1, "warn": 1, "fail": 1, "error": 0, "passed": False}
    assert body["findings"][1]["items"] == ["mlops-dev-a-tfstate"]


def test_search_volume_returns_summary(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        ops_router_module,
        "_run_bq_query",
        lambda project_id, sql_path: [
            {
                "n": "17",
                "first_ts": "2026-04-27 00:00:00+00:00",
                "last_ts": "2026-04-27 23:00:00+00:00",
            }
        ],
    )
    app = FastAPI()
    app.include_router(ops_router)
    client = TestClient(app)

    res = client.get("/ops/search-volume")

    assert res.status_code == 200
    assert res.json()["requests_24h"] == 17


def test_runs_recent_returns_rows(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        ops_router_module,
        "_run_bq_query",
        lambda project_id, sql_path: [
            {
                "run_id": "run-1",
                "finished_at": "2026-04-27 12:00:00+00:00",
                "ndcg_at_10": 0.91,
                "map": 0.72,
                "recall_at_20": 0.88,
                "model_path": "gs://bucket/model.txt",
            }
        ],
    )
    app = FastAPI()
    app.include_router(ops_router)
    client = TestClient(app)

    res = client.get("/ops/runs-recent")

    assert res.status_code == 200
    body = res.json()
    assert len(body["runs"]) == 1
    assert body["runs"][0]["run_id"] == "run-1"


def test_search_volume_returns_503_with_json_detail_on_bq_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        ops_router_module,
        "_run_bq_query",
        lambda project_id, sql_path: (_ for _ in ()).throw(RuntimeError("dataset missing")),
    )
    app = FastAPI()
    app.include_router(ops_router)
    client = TestClient(app)

    res = client.get("/ops/search-volume")

    assert res.status_code == 503
    assert res.json()["detail"] == "dataset missing"


def test_runs_recent_returns_503_with_json_detail_on_bq_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        ops_router_module,
        "_run_bq_query",
        lambda project_id, sql_path: (_ for _ in ()).throw(RuntimeError("dataset missing")),
    )
    app = FastAPI()
    app.include_router(ops_router)
    client = TestClient(app)

    res = client.get("/ops/runs-recent")

    assert res.status_code == 503
    assert res.json()["detail"] == "dataset missing"
