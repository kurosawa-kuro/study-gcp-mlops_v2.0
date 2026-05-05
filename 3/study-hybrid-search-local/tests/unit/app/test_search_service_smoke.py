"""Phase 3 — SearchService smoke test (Port-only、外部依存なし)."""

from __future__ import annotations

from app.domain.candidate import Candidate
from app.domain.search import SearchInput, SearchOutput
from app.services.protocols.search_cache import SearchCachePort
from app.services.protocols.synonym_expander import SynonymExpanderPort
from app.services.search_service import SearchService
from tests._fakes.in_memory_candidate_retriever import InMemoryCandidateRetriever
from tests._fakes.in_memory_ranking_log_publisher import InMemoryRankingLogPublisher
from tests._fakes.stub_encoder_client import StubEncoderClient


def test_search_service_returns_top_k_with_fallback() -> None:
    """fallback path (reranker=None) で /search が動くこと。"""
    candidates = [
        Candidate(
            property_id=f"prop-{i:03d}",
            lexical_rank=i + 1,
            semantic_rank=i + 1,
            me5_score=0.9 - i * 0.05,
            property_features={"rent": 100_000 + i * 1_000},
        )
        for i in range(5)
    ]
    retriever = InMemoryCandidateRetriever(candidates=candidates)
    encoder = StubEncoderClient(embedding_dim=8)
    publisher = InMemoryRankingLogPublisher()

    svc = SearchService(
        retriever_default=retriever,
        encoder=encoder,
        publisher=publisher,
        reranker=None,
        feature_fetcher=None,
    )
    output = svc.search(
        request_id="req-0001",
        input=SearchInput(query="駅近 1LDK", filters={}, top_k=3),
    )
    assert len(output.items) == 3
    assert output.items[0].lexical_rank == 1


class _StaticSynonymExpander(SynonymExpanderPort):
    """Returns a fixed expansion regardless of input — exercises the
    SearchService → SynonymExpanderPort → CandidateRetriever wiring."""

    def __init__(self, expanded: str) -> None:
        self._expanded = expanded

    def expand(self, query: str) -> str:
        return self._expanded


def test_search_service_routes_expanded_query_to_lexical_only() -> None:
    """SYN-1 invariant: expander が膨らませた query は retriever (lexical 側)
    に届く一方、encoder (semantic 側) は元のクエリを受け取る。"""
    retriever = InMemoryCandidateRetriever(
        candidates=[
            Candidate(
                property_id="prop-001",
                lexical_rank=1,
                semantic_rank=1,
                me5_score=0.9,
                property_features={},
            )
        ]
    )
    encoder = StubEncoderClient(embedding_dim=4)
    publisher = InMemoryRankingLogPublisher()
    svc = SearchService(
        retriever_default=retriever,
        encoder=encoder,
        publisher=publisher,
        reranker=None,
        feature_fetcher=None,
        synonym_expander=_StaticSynonymExpander("駅近 駅徒歩 アクセス良好"),
    )
    svc.search(
        request_id="req-syn",
        input=SearchInput(query="駅近", filters={}, top_k=5),
    )
    # retriever (lexical lane) は expanded query を受け取る
    assert retriever.calls[0].query_text == "駅近 駅徒歩 アクセス良好"
    # encoder (semantic lane) は元の query を受け取る
    assert encoder.calls[0].text == "駅近"
    assert encoder.calls[0].kind == "query"


def test_search_service_without_expander_passes_query_unchanged() -> None:
    """既定 (expander=None) では Phase 3 Wave 1-4 と挙動が変わらない。"""
    retriever = InMemoryCandidateRetriever(
        candidates=[
            Candidate(
                property_id="prop-002",
                lexical_rank=1,
                semantic_rank=1,
                me5_score=0.5,
                property_features={},
            )
        ]
    )
    encoder = StubEncoderClient(embedding_dim=4)
    publisher = InMemoryRankingLogPublisher()
    svc = SearchService(
        retriever_default=retriever,
        encoder=encoder,
        publisher=publisher,
        reranker=None,
        feature_fetcher=None,
    )
    svc.search(
        request_id="req-noexp",
        input=SearchInput(query="駅近", filters={}, top_k=5),
    )
    assert retriever.calls[0].query_text == "駅近"


# ----------------------------------------------------------- Phase 3 SYN-2


class _RecordingSearchCache(SearchCachePort):
    """In-memory ``SearchCachePort`` that records every get / set call."""

    def __init__(self, *, prepopulated: SearchOutput | None = None) -> None:
        self.gets: list[SearchInput] = []
        self.sets: list[tuple[SearchInput, SearchOutput]] = []
        self._stored: SearchOutput | None = prepopulated

    def get(self, request: SearchInput) -> SearchOutput | None:
        self.gets.append(request)
        return self._stored

    def set(self, request: SearchInput, output: SearchOutput) -> None:
        self.sets.append((request, output))
        self._stored = output


def _fixture_candidates() -> list[Candidate]:
    return [
        Candidate(
            property_id=f"prop-{i:03d}",
            lexical_rank=i + 1,
            semantic_rank=i + 1,
            me5_score=0.9 - i * 0.05,
            property_features={},
        )
        for i in range(3)
    ]


def test_search_service_miss_runs_pipeline_and_writes_cache() -> None:
    """SYN-2: cache MISS で encoder/retriever/publisher が動き、出力を Redis に書く。"""
    retriever = InMemoryCandidateRetriever(candidates=_fixture_candidates())
    encoder = StubEncoderClient(embedding_dim=4)
    publisher = InMemoryRankingLogPublisher()
    cache = _RecordingSearchCache()
    svc = SearchService(
        retriever_default=retriever,
        encoder=encoder,
        publisher=publisher,
        reranker=None,
        feature_fetcher=None,
        search_cache=cache,
    )
    output = svc.search(
        request_id="req-miss",
        input=SearchInput(query="駅近", filters={}, top_k=2),
    )
    # MISS → pipeline runs end-to-end
    assert len(retriever.calls) == 1
    assert len(encoder.calls) == 1
    # MISS → cache.set is called once with the output
    assert len(cache.sets) == 1
    assert cache.sets[0][1].request_id == "req-miss"
    assert len(output.items) == 2


def test_search_service_hit_short_circuits_pipeline_and_skips_publisher() -> None:
    """SYN-2: cache HIT で encoder/retriever/publisher が一切走らない。"""
    retriever = InMemoryCandidateRetriever(candidates=_fixture_candidates())
    encoder = StubEncoderClient(embedding_dim=4)
    publisher = InMemoryRankingLogPublisher()

    # First call populates the cache (MISS path).
    cache = _RecordingSearchCache()
    svc = SearchService(
        retriever_default=retriever,
        encoder=encoder,
        publisher=publisher,
        reranker=None,
        feature_fetcher=None,
        search_cache=cache,
    )
    request = SearchInput(query="駅近", filters={}, top_k=2)
    svc.search(request_id="req-1", input=request)
    miss_retriever_calls = len(retriever.calls)
    miss_encoder_calls = len(encoder.calls)
    miss_publisher_rows = len(publisher.calls)

    # Second identical call must be a HIT — no new pipeline activity.
    output = svc.search(request_id="req-2", input=request)
    assert len(retriever.calls) == miss_retriever_calls  # unchanged
    assert len(encoder.calls) == miss_encoder_calls
    assert len(publisher.calls) == miss_publisher_rows  # publisher skipped
    # Returned output uses the live request_id, not the original.
    assert output.request_id == "req-2"
    # Cache reads count: both calls did get(), only the first did set().
    assert len(cache.gets) == 2
    assert len(cache.sets) == 1


def test_search_service_with_no_cache_runs_live_every_time() -> None:
    """既定 (search_cache=None) では Wave 1-4 と挙動が変わらない。"""
    retriever = InMemoryCandidateRetriever(candidates=_fixture_candidates())
    encoder = StubEncoderClient(embedding_dim=4)
    publisher = InMemoryRankingLogPublisher()
    svc = SearchService(
        retriever_default=retriever,
        encoder=encoder,
        publisher=publisher,
        reranker=None,
        feature_fetcher=None,
    )
    request = SearchInput(query="駅近", filters={}, top_k=2)
    svc.search(request_id="req-1", input=request)
    svc.search(request_id="req-2", input=request)
    assert len(retriever.calls) == 2  # no caching, both run
    assert len(encoder.calls) == 2
