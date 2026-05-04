"""Phase 3 — SearchService smoke test (Port-only、外部依存なし)."""

from __future__ import annotations

from app.domain.candidate import Candidate
from app.domain.search import SearchInput
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
