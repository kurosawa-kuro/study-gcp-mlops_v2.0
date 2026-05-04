from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.search import SearchFilters
from app.services.adapters.lexical_search import MeilisearchLexical


def _fake_http_client() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {"hits": [{"property_id": "p001"}]}
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    client.post.return_value = response
    return client


def test_meili_lexical_uses_presigned_token_when_present(monkeypatch) -> None:
    monkeypatch.setenv("MEILI_PRESIGNED_ID_TOKEN", "preset-token")
    fake_client = _fake_http_client()
    with patch("app.services.adapters.lexical_search.httpx.Client", return_value=fake_client):
        adapter = MeilisearchLexical(
            base_url="https://meili.example.com",
            api_key="master-key",
            require_identity_token=True,
        )
        results = adapter.search(query="赤羽", filters=SearchFilters(), top_k=3)

    headers = fake_client.post.call_args.kwargs["headers"]
    assert headers["x-serverless-authorization"] == "Bearer preset-token"
    assert headers["authorization"] == "Bearer master-key"
    assert results[0].property_id == "p001"


def test_meili_lexical_can_mint_token_via_impersonation(monkeypatch) -> None:
    monkeypatch.delenv("MEILI_PRESIGNED_ID_TOKEN", raising=False)
    fake_client = _fake_http_client()
    fake_id_credentials = MagicMock()
    fake_id_credentials.token = "impersonated-token"
    with (
        patch("app.services.adapters.lexical_search.httpx.Client", return_value=fake_client),
        patch(
            "app.services.adapters.lexical_search.google_auth_default", return_value=(object(), "p")
        ),
        patch(
            "app.services.adapters.lexical_search.impersonated_credentials.Credentials",
            return_value=object(),
        ),
        patch(
            "app.services.adapters.lexical_search.impersonated_credentials.IDTokenCredentials",
            return_value=fake_id_credentials,
        ),
    ):
        adapter = MeilisearchLexical(
            base_url="https://meili.example.com",
            api_key="master-key",
            require_identity_token=True,
            impersonate_service_account="sa-api@example.iam.gserviceaccount.com",
        )
        adapter.search(query="赤羽", filters=SearchFilters(), top_k=3)

    headers = fake_client.post.call_args.kwargs["headers"]
    assert headers["x-serverless-authorization"] == "Bearer impersonated-token"
    assert headers["authorization"] == "Bearer master-key"
    fake_id_credentials.refresh.assert_called_once()
