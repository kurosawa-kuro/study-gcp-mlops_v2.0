"""Phase 3 — production noop / in-memory adapters.

これは「テスト用」ではなく「production 環境で adapter が disabled なときの fallback」。
test stubs は `tests/_fakes/` 側に分離されている。
"""

from .noop_feedback_recorder import NoopFeedbackRecorder
from .noop_lexical_search import NoopLexicalSearch
from .noop_ranking_log_publisher import NoopRankingLogPublisher

__all__ = [
    "NoopFeedbackRecorder",
    "NoopLexicalSearch",
    "NoopRankingLogPublisher",
]
