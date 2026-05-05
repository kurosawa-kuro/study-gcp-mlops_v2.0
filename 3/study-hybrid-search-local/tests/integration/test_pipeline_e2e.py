"""Phase 3 — Integration E2E (docker compose 立ち上げ済 + seed + train 完了前提).

`make verify-pipeline` から呼ばれる。

検証内容:
1. /health 200
2. /readyz が `rerank_enabled=true` (model.lgb 読み込み済み)
3. /search で lexical_rank / semantic_rank / final_rank が all non-zero
4. /search の rerank score が固定 fallback (None) でない (= 学習済 LightGBM 由来)
5. /feedback 200 を返す
6. ranking_log テーブルに row が 1 以上
"""

from __future__ import annotations

import os

import httpx
import psycopg
import pytest

API_BASE = os.environ.get("PHASE3_API_BASE", "http://localhost:8000")
POSTGRES_DSN = os.environ.get(
    "PHASE3_POSTGRES_DSN",
    "postgresql://admin:password@localhost:5433/hybrid_search",
)


def _api_alive() -> bool:
    try:
        r = httpx.get(f"{API_BASE}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _api_alive(),
    reason=f"Phase 3 search-api not reachable at {API_BASE} (run `make up && make seed && make train` and `docker compose up -d search-api` first)",
)


def test_health_returns_200() -> None:
    r = httpx.get(f"{API_BASE}/health", timeout=3.0)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_shows_rerank_enabled() -> None:
    r = httpx.get(f"{API_BASE}/readyz", timeout=3.0)
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "ready"
    assert payload["search_enabled"] is True
    assert payload["rerank_enabled"] is True, "model.lgb が読み込まれていない (make train 先行必須)"
    assert payload["model_path"], "model_path が空"


def test_search_returns_three_signal_all_non_zero() -> None:
    payload = {
        "query": "駅近 2LDK",
        "filters": {"max_rent": 200000, "layout": "2LDK"},
        "top_k": 5,
    }
    r = httpx.post(f"{API_BASE}/search", json=payload, timeout=15.0)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("results"), "/search が空 results を返した"
    assert len(body["results"]) <= 5

    # 3 系統 all non-zero (lexical / semantic / rerank)
    for item in body["results"]:
        assert item["lexical_rank"] >= 1, f"lexical_rank ゼロ: {item}"
        assert item["semantic_rank"] >= 1, f"semantic_rank ゼロ: {item}"
        assert item["final_rank"] >= 1, f"final_rank ゼロ: {item}"

    # rerank score が学習済モデル由来 (None = fallback ではない)
    scores = [item.get("score") for item in body["results"]]
    assert any(s is not None for s in scores), "全 score が None (rerank fallback してる)"


def test_feedback_returns_200() -> None:
    # ダミー request_id でも /feedback は受け付ける (ranking_log との外部キー制約は無い)
    payload = {
        "request_id": "phase3-e2e-test",
        "property_id": "prop-0001",
        "action": "click",
    }
    r = httpx.post(f"{API_BASE}/feedback", json=payload, timeout=5.0)
    assert r.status_code == 200, r.text


def test_ranking_log_persisted() -> None:
    """/search 実行後、ranking_log テーブルに row が永続化されている。"""
    # 念のため /search を 1 回実行 (state を作る)
    httpx.post(
        f"{API_BASE}/search",
        json={"query": "Tokyo 1LDK", "filters": {}, "top_k": 3},
        timeout=15.0,
    )
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ranking_log")
        row = cur.fetchone()
        assert row is not None
        count = int(row[0])
    assert count >= 1, f"ranking_log row が永続化されていない: count={count}"
