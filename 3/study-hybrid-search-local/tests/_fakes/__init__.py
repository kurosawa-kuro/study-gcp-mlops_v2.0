"""Phase 3 — test doubles for Port Protocols.

Phase 7 から流用 (``stub_popularity_scorer`` / ``stub_retrain_queries`` /
``mock_prediction_publisher`` は Phase 3 で対応 Port が除外されているため除外)。

Conventions:
- ``Stub*`` — deterministic constant return values (no state captured)
- ``Mock*`` — captures call arguments for later assertions
- ``InMemory*`` — full implementation backed by a dict / list
"""

from .in_memory_candidate_retriever import InMemoryCandidateRetriever
from .in_memory_feature_fetcher import InMemoryFeatureFetcher
from .in_memory_feedback_recorder import InMemoryFeedbackRecorder
from .in_memory_lexical_search import InMemoryLexicalSearch
from .in_memory_ranking_log_publisher import InMemoryRankingLogPublisher
from .in_memory_semantic_search import InMemorySemanticSearch
from .mock_reranker_client import MockRerankerClient
from .stub_encoder_client import StubEncoderClient

__all__ = [
    "InMemoryCandidateRetriever",
    "InMemoryFeatureFetcher",
    "InMemoryFeedbackRecorder",
    "InMemoryLexicalSearch",
    "InMemoryRankingLogPublisher",
    "InMemorySemanticSearch",
    "MockRerankerClient",
    "StubEncoderClient",
]
