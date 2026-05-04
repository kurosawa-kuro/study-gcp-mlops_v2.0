"""Production-grade null + in-memory adapter implementations.

These are real implementations of Port Protocols that ship to production
**when a feature flag is disabled** (Noop variants) or **when no external
backend is configured** (InMemory variants). They are NOT test doubles —
that is the role of ``tests/fakes/`` (Phase F-1).

Distinction:

- ``Noop*`` — accepts the call, does nothing, returns empty/None. Used
  when the corresponding feature is disabled (e.g. ``RANKING_LOG_TOPIC=""``
  → ``NoopRankingLogPublisher``).

Phase B-3 lifted these out of ``app/services/adapters/`` so callers can no
longer accidentally import a Noop while believing they have a production
adapter; the composition root selects each explicitly.
"""

from .noop_data_catalog_reader import NoopDataCatalogReader
from .noop_feedback_recorder import NoopFeedbackRecorder
from .noop_lexical_search import NoopLexicalSearch
from .noop_ranking_log_publisher import NoopRankingLogPublisher
from .noop_retrain_queries import NoopRetrainQueries

__all__ = [
    "NoopDataCatalogReader",
    "NoopFeedbackRecorder",
    "NoopLexicalSearch",
    "NoopRankingLogPublisher",
    "NoopRetrainQueries",
]
