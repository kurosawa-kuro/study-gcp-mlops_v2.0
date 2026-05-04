"""Test doubles for Port Protocols.

Distinction from ``app/services/noop_adapters/`` (production noop / in-memory):

- ``app/services/noop_adapters/`` ships to production when feature flags disable
  a backend (e.g. ``Noop*`` when a Pub/Sub topic is empty).
- ``tests/fakes/`` lives only in the test tree; classes here are
  deterministic stubs / call-recorders intended for asserting service-
  layer behaviour without touching real adapters.

Conventions:

- ``Stub*`` — deterministic constant return values (no state captured).
- ``Mock*`` — captures call arguments for later assertions.
- ``InMemory*`` — full implementation backed by a dict / list, useful
  when the test exercises round-trip read-back.

Each class implements exactly one Port and accepts plain Python types
so individual tests can construct them inline without builders.
"""

from .in_memory_candidate_retriever import InMemoryCandidateRetriever
from .in_memory_feature_fetcher import InMemoryFeatureFetcher
from .in_memory_feedback_recorder import InMemoryFeedbackRecorder
from .in_memory_lexical_search import InMemoryLexicalSearch
from .in_memory_ranking_log_publisher import InMemoryRankingLogPublisher
from .in_memory_semantic_search import InMemorySemanticSearch
from .mock_prediction_publisher import MockPredictionPublisher
from .mock_reranker_client import MockRerankerClient
from .stub_encoder_client import StubEncoderClient
from .stub_popularity_scorer import StubPopularityScorer
from .stub_retrain_queries import StubRetrainQueries

__all__ = [
    "InMemoryCandidateRetriever",
    "InMemoryFeatureFetcher",
    "InMemoryFeedbackRecorder",
    "InMemoryLexicalSearch",
    "InMemoryRankingLogPublisher",
    "InMemorySemanticSearch",
    "MockPredictionPublisher",
    "MockRerankerClient",
    "StubEncoderClient",
    "StubPopularityScorer",
    "StubRetrainQueries",
]
