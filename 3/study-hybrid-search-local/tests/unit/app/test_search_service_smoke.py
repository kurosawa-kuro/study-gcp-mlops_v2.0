"""Phase 3 — SearchService smoke test (Port-only、外部依存なし)."""

from __future__ import annotations

from app.domain.candidate import Candidate
from app.domain.search import SearchInput
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
