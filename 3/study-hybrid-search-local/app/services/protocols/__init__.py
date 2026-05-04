"""Phase 3 — API-side Ports (Phase 7 から流用、Phase 3 で必要なもののみ).

Phase 7 で定義された 13 Port のうち、Phase 3 で使うのは以下の 8 本:
- LexicalSearchPort (Meilisearch)
- SemanticSearchPort (pgvector)
- EncoderClient (multilingual-e5)
- RerankerClient / RerankerExplainer (LightGBM in-process)
- FeatureFetcher / FeatureRow (PostgreSQL feature_mart)
- RankingLogPublisher (PostgreSQL ranking_log)
- FeedbackRecorder (PostgreSQL feedback_events)
- CandidateRetriever (LocalCandidateRetriever = lexical + semantic + RRF を統合)

Phase 7 にあった以下の Port は Phase 3 では除外 (引き算):
- PopularityScorer (BQML 専用、Phase 6 論理 / Phase 7 本実装)
- DataCatalogReader (BigQuery メタデータ専用)
- PredictionPublisher / NoopPublisher (Pub/Sub 予測ログ、Phase 4 以降)
- RetrainQueries (BQ retrain orchestration、Phase 6 / 7)
"""

from .candidate_retriever import CandidateRetriever
from .encoder_client import EncoderClient
from .feature_fetcher import FeatureFetcher, FeatureRow
from .feedback_recorder import FeedbackRecorder
from .lexical_search import LexicalSearchPort
from .ranking_log_publisher import RankingLogPublisher
from .reranker_client import RerankerClient, RerankerExplainer
from .semantic_search import SemanticSearchPort

__all__ = [
    "CandidateRetriever",
    "EncoderClient",
    "FeatureFetcher",
    "FeatureRow",
    "FeedbackRecorder",
    "LexicalSearchPort",
    "RankingLogPublisher",
    "RerankerClient",
    "RerankerExplainer",
    "SemanticSearchPort",
]
