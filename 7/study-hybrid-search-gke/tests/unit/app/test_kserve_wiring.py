"""Phase 7 composition-root + ApiSettings wiring for KServe adapters.

These tests pin down the contract between ``app.settings.ApiSettings``
(env var → attribute) and ``ContainerBuilder._build_*_client`` (settings →
``KServeEncoder`` / ``KServeReranker``). They run purely in-process, with no
GCP calls or kubectl.

Why this layer matters: Phase 7 introduces three new env-driven knobs
(``KSERVE_ENCODER_URL`` / ``KSERVE_RERANKER_URL`` / ``KSERVE_RERANKER_EXPLAIN_URL``).
Silent wiring regressions here surface as 503 on ``/search`` in production,
so the wiring needs explicit coverage independent of the adapter unit tests.
"""

from __future__ import annotations

import pytest

from app.composition_root import ContainerBuilder
from app.services.adapters import KServeEncoder, KServeReranker
from app.settings import ApiSettings


def _settings(**overrides: object) -> ApiSettings:
    # Build ApiSettings from explicit kwargs so we don't depend on the process env.
    base: dict[str, object] = {
        "enable_search": True,
        "enable_rerank": True,
        "kserve_encoder_url": "",
        "kserve_reranker_url": "",
        "kserve_reranker_explain_url": "",
        "kserve_predict_timeout_seconds": 30.0,
    }
    base.update(overrides)
    return ApiSettings(**base)  # type: ignore[arg-type]


def _build_encoder_client(settings: ApiSettings):
    return ContainerBuilder(settings)._build_encoder_client()


def _build_reranker_client(settings: ApiSettings):
    return ContainerBuilder(settings)._build_reranker_client()


# ----------------------------------------------------------------------------
# ApiSettings field defaults
# ----------------------------------------------------------------------------


def test_apisettings_kserve_fields_default_to_empty_string() -> None:
    """Defaults: the Phase 7 KServe URL fields must default to empty string
    (not None / not a hardcoded cluster-local URL) so the composition root's
    empty-string gate (disable rerank / encoder when URL is missing) behaves
    correctly on a fresh environment without env vars.
    """
    settings = ApiSettings()
    assert settings.kserve_encoder_url == ""
    assert settings.kserve_reranker_url == ""
    assert settings.kserve_reranker_explain_url == ""
    assert settings.kserve_predict_timeout_seconds == 30.0
    assert settings.kserve.encoder_url == ""
    assert settings.kserve.reranker_url == ""
    assert settings.kserve.reranker_explain_url == ""
    assert settings.kserve.predict_timeout_seconds == 30.0


def test_apisettings_kserve_fields_populated_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """pydantic-settings env binding: ``KSERVE_*_URL`` env vars must land on
    the matching ApiSettings attribute (case-insensitive via pydantic-settings
    default behavior).
    """
    monkeypatch.setenv(
        "KSERVE_ENCODER_URL",
        "http://property-encoder.kserve-inference.svc.cluster.local/v1/models/property-encoder:predict",
    )
    monkeypatch.setenv(
        "KSERVE_RERANKER_URL",
        "http://property-reranker.kserve-inference.svc.cluster.local/v1/models/property-reranker:predict",
    )
    monkeypatch.setenv(
        "KSERVE_RERANKER_EXPLAIN_URL",
        "http://property-reranker.kserve-inference.svc.cluster.local/v1/models/property-reranker:explain",
    )
    monkeypatch.setenv("KSERVE_PREDICT_TIMEOUT_SECONDS", "45.0")

    settings = ApiSettings()
    assert "property-encoder.kserve-inference.svc.cluster.local" in settings.kserve_encoder_url
    assert ":predict" in settings.kserve_reranker_url
    assert ":explain" in settings.kserve_reranker_explain_url
    assert settings.kserve_predict_timeout_seconds == 45.0
    assert "property-encoder.kserve-inference.svc.cluster.local" in settings.kserve.encoder_url
    assert ":predict" in settings.kserve.reranker_url
    assert ":explain" in settings.kserve.reranker_explain_url
    assert settings.kserve.predict_timeout_seconds == 45.0


def test_apisettings_exposes_grouped_views_for_flags_messaging_and_popularity() -> None:
    settings = ApiSettings(
        enable_search=True,
        enable_rerank=True,
        ranking_log_topic="ranking-log",
        feedback_topic="search-feedback",
        retrain_topic="retrain-trigger",
        bqml_popularity_enabled=True,
        bqml_popularity_model_fqn="p.mlops.property_popularity",
    )

    assert settings.feature_flags.enable_search is True
    assert settings.feature_flags.enable_rerank is True
    assert settings.messaging.ranking_log_topic == "ranking-log"
    assert settings.messaging.feedback_topic == "search-feedback"
    assert settings.messaging.retrain_topic == "retrain-trigger"
    assert settings.popularity.enabled is True
    assert settings.popularity.model_fqn == "p.mlops.property_popularity"


# ----------------------------------------------------------------------------
# _build_encoder_client
# ----------------------------------------------------------------------------


def test_build_encoder_client_returns_none_when_url_empty() -> None:
    """Empty URL must produce (None, None) without raising. The /search path
    downstream treats None as disabled and returns 503 on first call."""
    client, name = _build_encoder_client(_settings(kserve_encoder_url=""))
    assert client is None
    assert name is None


def test_build_encoder_client_instantiates_kserve_encoder_when_url_set() -> None:
    client, name = _build_encoder_client(
        _settings(
            kserve_encoder_url="http://property-encoder.kserve-inference.svc.cluster.local/predict",
        )
    )
    assert isinstance(client, KServeEncoder)
    assert client.endpoint_url.endswith("/predict")
    assert name == client.endpoint_name


# ----------------------------------------------------------------------------
# _build_reranker_client (the Phase 7 change that added explain_url wiring)
# ----------------------------------------------------------------------------


def test_build_reranker_client_returns_none_when_enable_rerank_false() -> None:
    client, name = _build_reranker_client(_settings(enable_rerank=False))
    assert client is None
    assert name is None


def test_build_reranker_client_returns_none_when_url_empty() -> None:
    client, name = _build_reranker_client(_settings(enable_rerank=True, kserve_reranker_url=""))
    assert client is None
    assert name is None


def test_build_reranker_client_instantiates_with_explain_url_when_set() -> None:
    """When ``KSERVE_RERANKER_EXPLAIN_URL`` is set, the constructed adapter
    must carry that explain URL — critical for the Phase 6 T4 explain path to
    dispatch via a dedicated /explain route instead of parameters.explain=true.
    """
    client, _ = _build_reranker_client(
        _settings(
            enable_rerank=True,
            kserve_reranker_url="http://r.x/v1/models/m:predict",
            kserve_reranker_explain_url="http://r.x/v1/models/m:explain",
        )
    )
    assert isinstance(client, KServeReranker)
    assert client.endpoint_url == "http://r.x/v1/models/m:predict"
    assert client.explain_url == "http://r.x/v1/models/m:explain"


def test_build_reranker_client_passes_none_when_explain_url_is_empty_string() -> None:
    """The composition root uses ``explain_url=settings.kserve_reranker_explain_url or None``.
    This test pins that ``""`` converts to ``None`` (not the empty string) so
    ``KServeReranker.__init__`` sees the fallback-to-parameters.explain=true
    branch, not a bogus empty URL.
    """
    client, _ = _build_reranker_client(
        _settings(
            enable_rerank=True,
            kserve_reranker_url="http://r.x/v1/models/m:predict",
            kserve_reranker_explain_url="",
        )
    )
    assert isinstance(client, KServeReranker)
    assert client.explain_url is None


def test_build_reranker_client_handles_whitespace_explain_url() -> None:
    """``KServeReranker.__init__`` strips whitespace-only strings to ``""`` and
    rejects empty endpoint_url; for the optional explain_url, an all-whitespace
    value should behave like None.
    """
    client, _ = _build_reranker_client(
        _settings(
            enable_rerank=True,
            kserve_reranker_url="http://r.x/predict",
            # whitespace is stripped to "", then `or None` → None
            kserve_reranker_explain_url="   ",
        )
    )
    assert isinstance(client, KServeReranker)
    # `or None` catches only "", but `ApiSettings` keeps strings as-is;
    # `KServeReranker(explain_url="   ")` would strip to "" and assign None.
    assert client.explain_url is None


def test_build_reranker_client_has_predict_with_explain_for_ranking_gate() -> None:
    """Regression guard for the ``ranking.py`` ``hasattr(reranker,
    "predict_with_explain")`` gate: the Phase 7 reranker client must expose
    the method so ``/search?explain=true`` dispatches through the explain
    branch (Phase 6 T4 invariant).
    """
    client, _ = _build_reranker_client(
        _settings(enable_rerank=True, kserve_reranker_url="http://r.x/predict")
    )
    assert client is not None
    assert callable(getattr(client, "predict_with_explain", None))
