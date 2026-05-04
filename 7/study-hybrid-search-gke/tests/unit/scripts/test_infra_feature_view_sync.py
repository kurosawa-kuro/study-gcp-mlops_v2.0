from __future__ import annotations

import json
from unittest.mock import patch

from scripts.infra import feature_view_sync as fvs


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_main_skips_when_fos_outputs_are_empty(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PROJECT_ID", "mlops-test")
    with patch.object(
        fvs,
        "_terraform_output_map",
        return_value={"vertex_feature_online_store_id": "", "vertex_feature_view_id": ""},
    ):
        assert fvs.main() == 0
    assert "FeatureView sync skipped" in capsys.readouterr().out


def test_trigger_and_wait_posts_sync_then_polls_until_complete() -> None:
    calls: list[str] = []

    def _fake_urlopen(req, timeout=60):
        url = req.full_url
        calls.append(f"{req.get_method()} {url}")
        if url.endswith(":sync"):
            return _FakeResponse(b"{}")
        if "pageSize=1" in url:
            return _FakeResponse(json.dumps({"featureViewSyncs": [{"name": "old-sync"}]}).encode())
        return _FakeResponse(
            json.dumps(
                {
                    "featureViewSyncs": [
                        {
                            "name": "new-sync",
                            "runTime": {
                                "startTime": "2026-05-02T00:00:00Z",
                                "endTime": "2026-05-02T00:01:00Z",
                            },
                            "finalStatus": {"code": 0},
                        }
                    ]
                }
            ).encode()
        )

    with (
        patch.object(fvs, "_access_token", return_value="tok"),
        patch("urllib.request.urlopen", side_effect=_fake_urlopen),
    ):
        fvs.trigger_and_wait(
            project_id="mlops-test",
            region="asia-northeast1",
            store_id="store-a",
            view_id="view-a",
            timeout_sec=30,
            poll_sec=0,
        )

    assert any(":sync" in call for call in calls)
    assert any("featureViewSyncs?pageSize=5" in call for call in calls)
