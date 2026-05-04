"""Phase 3 — production adapter implementations.

すべて Local Docker Compose で動く実装。Port は ``app/services/protocols/`` 側、
Phase 7 と完全同型。Phase 4 で adapter ファイルを Cloud SDK 版に追加 (置換ではなく
別ファイルとして並行追加し、composition_root の選択ロジックで切替) する想定。
"""

from .local_candidate_retriever import LocalCandidateRetriever
from .local_e5_encoder import LocalE5Encoder
from .local_lightgbm_reranker import LocalLightGBMReranker
from .meilisearch_lexical_search import MeilisearchLexicalSearch
from .pgvector_semantic_search import PgVectorSemanticSearch
from .postgres_feature_fetcher import PostgresFeatureFetcher
from .postgres_feedback_recorder import PostgresFeedbackRecorder
from .postgres_ranking_log_publisher import PostgresRankingLogPublisher

__all__ = [
    "LocalCandidateRetriever",
    "LocalE5Encoder",
    "LocalLightGBMReranker",
    "MeilisearchLexicalSearch",
    "PgVectorSemanticSearch",
    "PostgresFeatureFetcher",
    "PostgresFeedbackRecorder",
    "PostgresRankingLogPublisher",
]
