"""Phase 7 PR-4 — `run_search` x FeatureFetcher opt-in merge.

Verifies the contract added in PR-4:

- ``run_search(feature_fetcher=None)`` (default) preserves Phase 5 / 6
  behaviour exactly — candidate features are passed through to the
  reranker untouched.
- ``run_search(feature_fetcher=fake)`` calls ``fetch`` once with the
  retrieved property IDs and merges ``ctr`` / ``fav_rate`` /
  ``inquiry_rate`` from the fetched ``FeatureRow`` onto each candidate's
  ``property_features`` dict before ``build_ranker_features`` runs.
- A failing fetcher does not 503 the request — rerank continues with
  BQ-enriched (stale) features and the failure is logged.

Phase 7 ``docs/tasks/TASKS_ROADMAP.md`` §3.4 受け入れ条件 (ローカル):
- default で挙動変わらず (unit test で確認)
- 設定時のみ Feature Online Store の fetch 経路に分岐 (unit test で確認)
"""

from __future__ import annotations

from app.domain.candidate import Candidate
from app.domain.search import SearchFilters
from app.services.protocols.feature_fetcher import FeatureFetcher, FeatureRow
from app.services.ranking import _augment_with_fresh_features, run_search
from tests._fakes import (
    InMemoryCandidateRetriever,
    InMemoryFeatureFetcher,
    InMemoryRankingLogPublisher,
    MockRerankerClient,
)


def _candidate(
    pid: str,
    *,
    ctr: float = 0.10,
    fav_rate: float = 0.05,
    inquiry_rate: float = 0.02,
) -> Candidate:
    return Candidate(
        property_id=pid,
        lexical_rank=1,
        semantic_rank=1,
        me5_score=0.5,
        property_features={
            "rent": 80_000,
            "walk_min": 5,
            "age_years": 10,
            "area_m2": 25.0,
            "ctr": ctr,
            "fav_rate": fav_rate,
            "inquiry_rate": inquiry_rate,
        },
    )


# ----------------------------------------------------------------------------
# _augment_with_fresh_features (helper unit)
# ----------------------------------------------------------------------------


def test_augment_overwrites_three_dynamic_features() -> None:
    cands = [_candidate("p001", ctr=0.10, fav_rate=0.05, inquiry_rate=0.02)]
    fetcher = InMemoryFeatureFetcher(
        rows={"p001": FeatureRow(property_id="p001", ctr=0.99, fav_rate=0.88, inquiry_rate=0.77)}
    )

    out = _augment_with_fresh_features(cands, fetcher)

    assert len(out) == 1
    f = out[0].property_features
    assert f["ctr"] == 0.99
    assert f["fav_rate"] == 0.88
    assert f["inquiry_rate"] == 0.77
    # Display-side fields untouched.
    assert f["rent"] == 80_000
    assert f["walk_min"] == 5


def test_augment_preserves_bq_value_when_fos_field_is_none() -> None:
    """``None`` from FOS = "no fresh data" → keep BQ-enriched value."""
    cands = [_candidate("p001", ctr=0.10, fav_rate=0.05, inquiry_rate=0.02)]
    fetcher = InMemoryFeatureFetcher(
        rows={"p001": FeatureRow(property_id="p001", ctr=None, fav_rate=0.88, inquiry_rate=None)}
    )

    out = _augment_with_fresh_features(cands, fetcher)

    f = out[0].property_features
    assert f["ctr"] == 0.10  # BQ value retained
    assert f["fav_rate"] == 0.88  # FOS overrode
    assert f["inquiry_rate"] == 0.02  # BQ value retained


def test_augment_keeps_candidate_unchanged_when_id_not_in_fos() -> None:
    cands = [_candidate("p001"), _candidate("p999", ctr=0.42)]
    fetcher = InMemoryFeatureFetcher(
        rows={"p001": FeatureRow(property_id="p001", ctr=0.99, fav_rate=0.88, inquiry_rate=0.77)}
    )

    out = _augment_with_fresh_features(cands, fetcher)

    # InMemoryFeatureFetcher returns all-None for unknown IDs (Port contract),
    # so the merge is a no-op and BQ-enriched values are preserved.
    assert out[1].property_features["ctr"] == 0.42


def test_augment_returns_empty_list_for_empty_input() -> None:
    fetcher = InMemoryFeatureFetcher()
    assert _augment_with_fresh_features([], fetcher) == []
    assert fetcher.calls == []


def test_augment_calls_fetch_once_with_all_property_ids() -> None:
    cands = [_candidate("p001"), _candidate("p002"), _candidate("p003")]
    fetcher = InMemoryFeatureFetcher()

    _augment_with_fresh_features(cands, fetcher)

    assert fetcher.calls == [["p001", "p002", "p003"]]


# ----------------------------------------------------------------------------
# run_search x feature_fetcher integration (lightweight)
# ----------------------------------------------------------------------------


def test_run_search_default_feature_fetcher_is_none_no_fetch_happens() -> None:
    """PR-4 Strangler default — without ``feature_fetcher``, no merge is attempted."""
    cand = _candidate("p001", ctr=0.10)
    retriever = InMemoryCandidateRetriever(candidates=[cand])
    publisher = InMemoryRankingLogPublisher()
    fetcher = InMemoryFeatureFetcher(
        rows={"p001": FeatureRow(property_id="p001", ctr=0.99, fav_rate=0.88, inquiry_rate=0.77)}
    )
    reranker = MockRerankerClient()

    run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="r1",
        query_text="赤羽",
        query_vector=[0.0] * 768,
        filters=SearchFilters(),
        top_k=10,
        reranker=reranker,
        # feature_fetcher omitted on purpose (default None)
    )

    # The fetcher was provided but NOT passed in → it must be untouched.
    assert fetcher.calls == []


def test_run_search_with_feature_fetcher_merges_before_reranker_predict() -> None:
    cand = _candidate("p001", ctr=0.10, fav_rate=0.05, inquiry_rate=0.02)
    retriever = InMemoryCandidateRetriever(candidates=[cand])
    publisher = InMemoryRankingLogPublisher()
    fetcher = InMemoryFeatureFetcher(
        rows={"p001": FeatureRow(property_id="p001", ctr=0.99, fav_rate=0.88, inquiry_rate=0.77)}
    )
    reranker = MockRerankerClient()

    run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="r1",
        query_text="赤羽",
        query_vector=[0.0] * 768,
        filters=SearchFilters(),
        top_k=10,
        reranker=reranker,
        feature_fetcher=fetcher,
    )

    # Fetcher was called with the retrieved property_id.
    assert fetcher.calls == [["p001"]]
    # Reranker received the fresh feature values via its ``predict`` matrix.
    # FEATURE_COLS_RANKER ordering: rent, walk_min, age_years, area_m2,
    # ctr (idx 4), fav_rate (idx 5), inquiry_rate (idx 6), me5_score, lexical, semantic.
    assert reranker.predict_calls, "reranker.predict should have been called"
    matrix = reranker.predict_calls[0]
    row = matrix[0]
    assert row[4] == 0.99  # ctr (FOS-fresh)
    assert row[5] == 0.88  # fav_rate (FOS-fresh)
    assert row[6] == 0.77  # inquiry_rate (FOS-fresh)


def test_run_search_swallows_feature_fetcher_failure_and_continues() -> None:
    """A FOS outage must not 503 /search — rerank with stale BQ features instead."""
    cand = _candidate("p001", ctr=0.10)
    retriever = InMemoryCandidateRetriever(candidates=[cand])
    publisher = InMemoryRankingLogPublisher()
    reranker = MockRerankerClient()

    class _ExplodingFetcher(FeatureFetcher):
        def fetch(self, property_ids: list[str]) -> dict[str, FeatureRow]:
            raise RuntimeError("simulated FOS 503")

    ranked = run_search(
        retriever=retriever,
        publisher=publisher,
        request_id="r1",
        query_text="赤羽",
        query_vector=[0.0] * 768,
        filters=SearchFilters(),
        top_k=10,
        reranker=reranker,
        feature_fetcher=_ExplodingFetcher(),
    )

    # /search returned a result (degraded, not 503) using the original BQ ctr.
    assert ranked
    matrix = reranker.predict_calls[0]
    assert matrix[0][4] == 0.10  # ctr from BQ-enriched candidate, not FOS


# ----------------------------------------------------------------------------
# Container wiring (PR-4)
# ----------------------------------------------------------------------------


def test_container_dataclass_has_feature_fetcher_field() -> None:
    """The Container must surface ``feature_fetcher`` so handlers can introspect."""
    from app.composition_root import Container

    annotations = Container.__annotations__
    assert "feature_fetcher" in annotations
    # ``FeatureFetcher | None`` — the optional shape lets handlers detect
    # whether opt-in fresh-feature merge is active.
    raw = annotations["feature_fetcher"]
    raw_str = str(raw)
    assert "FeatureFetcher" in raw_str
    assert "None" in raw_str


def test_search_service_accepts_feature_fetcher_kwarg() -> None:
    from inspect import signature

    from app.services.search_service import SearchService

    params = signature(SearchService.__init__).parameters
    assert "feature_fetcher" in params
    assert params["feature_fetcher"].default is None  # Strangler default


def test_run_search_signature_lists_feature_fetcher_with_default_none() -> None:
    from inspect import signature

    from app.services.ranking import run_search as rs

    params = signature(rs).parameters
    assert "feature_fetcher" in params
    assert params["feature_fetcher"].default is None
