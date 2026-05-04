"""Unit tests for Vertex Feature Store async-delete polling."""

from __future__ import annotations

import pytest

from scripts.infra import vertex_feature_store_wait as vfs


def test_wait_until_feature_store_names_released_exits_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def fake_token() -> str:
        return "tok"

    def fake_rest(_token: str, url: str) -> dict:
        calls["n"] += 1
        if "featureGroups" in url:
            return {"featureGroups": []}
        if "featureOnlineStores" in url:
            return {"featureOnlineStores": []}
        return {}

    monkeypatch.setattr(vfs, "_access_token", fake_token)
    monkeypatch.setattr(vfs, "_rest_get", fake_rest)

    vfs.wait_until_feature_store_names_released(
        "p",
        "asia-northeast1",
        timeout_seconds=5,
        poll_seconds=1,
    )
    assert calls["n"] >= 2


def test_wait_until_feature_store_names_released_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_token() -> str:
        return "tok"

    def fake_rest(_token: str, url: str) -> dict:
        if "featureGroups" in url:
            return {
                "featureGroups": [
                    {"name": "projects/p/locations/asia-northeast1/featureGroups/property_features"}
                ]
            }
        if "featureOnlineStores" in url:
            return {"featureOnlineStores": []}
        return {}

    monkeypatch.setattr(vfs, "_access_token", fake_token)
    monkeypatch.setattr(vfs, "_rest_get", fake_rest)
    monkeypatch.setattr(vfs.time, "sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="still listed"):
        vfs.wait_until_feature_store_names_released(
            "p",
            "asia-northeast1",
            timeout_seconds=1,
            poll_seconds=0,
        )
