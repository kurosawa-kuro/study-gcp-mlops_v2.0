"""Pure orchestration for /search.

Two rerank modes coexist:

* **Fallback** (``reranker=None``): ``final_rank = lexical_rank``.
* **Vertex rerank** (``reranker`` supplied): ranker features are assembled and
  passed to the reranker port, which returns one score per candidate.

The ranking_log publisher always receives the full candidate pool plus the
score list (``None`` in fallback mode) so offline evaluation can compare
both regimes during rollout.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.domain.candidate import Candidate, RankedCandidate
from app.domain.search import SearchFilters
from app.services.protocols.candidate_retriever import CandidateRetriever
from app.services.protocols.feature_fetcher import FeatureFetcher
from app.services.protocols.ranking_log_publisher import RankingLogPublisher
from app.services.protocols.reranker_client import RerankerClient, RerankerExplainer
from ml.common.logging import get_logger
from ml.data.feature_engineering import FEATURE_COLS_RANKER, build_ranker_features

logger = get_logger("app.ranking")


def _safe_publish_candidates(
    publisher: RankingLogPublisher,
    *,
    request_id: str,
    candidates: list[Candidate],
    final_ranks: list[int],
    scores: list[float | None],
    model_path: str | None,
) -> None:
    """Publish ranking_log rows; swallow failures so /search keeps serving.

    Adapter-level (``PubSubRankingLogPublisher.publish_candidates``)
    raises with a loud ``log_publish_failure`` ERROR log + IAM hints
    (Phase 6 Run 1 incident pattern). At the service-orchestration layer
    we swallow so a Pub/Sub topic / IAM regression does not turn /search
    into a 500 for end users — matching ``FeedbackService.record`` which
    already treats publish as best-effort telemetry.

    The ERROR log is still emitted by ``log_publish_failure`` so
    operators see it; ranking_log just gets gaps until ops restores the
    publish path.
    """
    try:
        publisher.publish_candidates(
            request_id=request_id,
            candidates=candidates,
            final_ranks=final_ranks,
            scores=scores,
            model_path=model_path,
        )
    except Exception:
        logger.exception(
            "ranking_log publish failed — continuing /search (request_id=%s, "
            "candidates=%d). Adapter ERROR log carries the IAM / topic hint.",
            request_id,
            len(candidates),
        )


RRF_K: int = 60

# Phase E moved ``RankedCandidate`` to ``app.domain.candidate``. Re-exported
# here for legacy callers; Phase D-1 sweeps these into ``SearchService``
# directly.
__all__ = [
    "RRF_K",
    "Candidate",
    "RankedCandidate",
    "rrf_fuse",
    "run_search",
]


def _augment_with_fresh_features(
    candidates: list[Candidate],
    feature_fetcher: FeatureFetcher,
) -> list[Candidate]:
    """Overwrite ``ctr`` / ``fav_rate`` / ``inquiry_rate`` from a fresher source.

    Phase 7 PR-4: when a Vertex AI Feature Online Store fetcher is wired in
    (see ``SearchBuilder.resolve_feature_fetcher``), call it once per
    /search to get the latest behavioural signals and merge them onto the
    BigQuery-enriched ``Candidate.property_features`` dict before
    ``build_ranker_features`` runs.

    Why merge instead of replace:
    - ``BigQueryCandidateRetriever`` populates display-side fields (rent /
      walk_min / age_years / area_m2 / title / city / ...) from
      ``properties_cleaned`` that are NOT served by Feature Online Store.
    - FOS only owns the 3 dynamic columns in ``FeatureRow``.
    - Replacing the entire dict would drop everything else.

    Failure semantics:
    - ``feature_fetcher.fetch`` raising propagates to ``run_search``
      caller (decision: skip rerank vs return 503 belongs upstream).
    - ``FeatureRow`` fields equal to ``None`` are skipped (treat as "no
      fresh data", keep BQ-enriched value).
    """
    if not candidates:
        return candidates
    rows = feature_fetcher.fetch([c.property_id for c in candidates])
    out: list[Candidate] = []
    for cand in candidates:
        row = rows.get(cand.property_id)
        if row is None:
            out.append(cand)
            continue
        merged = dict(cand.property_features)
        if row.ctr is not None:
            merged["ctr"] = row.ctr
        if row.fav_rate is not None:
            merged["fav_rate"] = row.fav_rate
        if row.inquiry_rate is not None:
            merged["inquiry_rate"] = row.inquiry_rate
        out.append(replace(cand, property_features=merged))
    return out


def _build_feature_matrix(candidates: list[Candidate]) -> list[list[float]]:
    """Build the feature matrix in FEATURE_COLS_RANKER order."""
    rows = [
        build_ranker_features(
            property_features=cand.property_features,
            me5_score=cand.me5_score,
            lexical_rank=cand.lexical_rank,
            semantic_rank=cand.semantic_rank,
        )
        for cand in candidates
    ]
    return [[float(row[col]) for col in FEATURE_COLS_RANKER] for row in rows]


def _score_candidates(candidates: list[Candidate], reranker: RerankerClient) -> list[float]:
    matrix = _build_feature_matrix(candidates)
    return reranker.predict(matrix)


def _score_with_explain(
    candidates: list[Candidate],
    reranker: RerankerExplainer,
) -> tuple[list[float], list[dict[str, float]]]:
    matrix = _build_feature_matrix(candidates)
    return reranker.predict_with_explain(matrix, FEATURE_COLS_RANKER)


def run_search(
    *,
    retriever: CandidateRetriever,
    publisher: RankingLogPublisher,
    request_id: str,
    query_text: str,
    query_vector: list[float],
    filters: SearchFilters,
    top_k: int,
    reranker: RerankerClient | None = None,
    model_path: str | None = None,
    want_explanations: bool = False,
    feature_fetcher: FeatureFetcher | None = None,
) -> list[RankedCandidate]:
    """Execute one search and return ranked candidates truncated to top_k.

    If ``reranker`` is ``None`` the fallback path kicks in.
    Either way, ranking_log receives one row per retrieved candidate (not just
    the top_k) so offline eval keeps the full pool.

    ``want_explanations=True`` plus a reranker that satisfies
    ``RerankerExplainer`` (has ``predict_with_explain``) attaches per-instance
    TreeSHAP attributions to each returned ``RankedCandidate``. A reranker
    that only implements plain ``predict`` silently falls back to no
    attributions so existing Phase 5 deployments keep working.
    """
    candidates = retriever.retrieve(
        query_text=query_text,
        query_vector=query_vector,
        filters=filters,
        top_k=top_k,
    )
    # Phase 7 PR-4 — opt-in fresh feature fetch (default off when fetcher is None,
    # i.e. composition root did not wire FOS). Failures here propagate so /search
    # signals 503 rather than rerank with stale features.
    if feature_fetcher is not None and candidates:
        try:
            candidates = _augment_with_fresh_features(candidates, feature_fetcher)
        except Exception:
            logger.exception(
                "feature_fetcher.fetch failed for request_id=%s — continuing rerank "
                "with BigQuery-enriched features (degraded freshness, not 503).",
                request_id,
            )
    if not candidates:
        _safe_publish_candidates(
            publisher,
            request_id=request_id,
            candidates=[],
            final_ranks=[],
            scores=[],
            model_path=model_path if reranker is not None else None,
        )
        return []

    if reranker is not None:
        attributions: list[dict[str, float]] | None = None
        if want_explanations and hasattr(reranker, "predict_with_explain"):
            scores, attributions = _score_with_explain(
                candidates,
                reranker,  # type: ignore[arg-type]
            )
        else:
            scores = _score_candidates(candidates, reranker)
        # Stable descending sort; higher score wins. Ties preserve lexical order
        # because ``sorted`` is stable and candidates are already lexically ordered.
        order = sorted(range(len(candidates)), key=lambda i: -scores[i])
        final_rank_by_index = {i: rank + 1 for rank, i in enumerate(order)}
        # publish in lexical (original) order so ranking_log matches the
        # candidates' `lexical_rank` column 1:1.
        scores_nullable: list[float | None] = list(scores)
        _safe_publish_candidates(
            publisher,
            request_id=request_id,
            candidates=candidates,
            final_ranks=[final_rank_by_index[i] for i in range(len(candidates))],
            scores=scores_nullable,
            model_path=model_path,
        )
        ranked = [
            RankedCandidate(
                candidate=candidates[i],
                final_rank=final_rank_by_index[i],
                score=scores[i],
                attributions=(attributions[i] if attributions is not None else None),
            )
            for i in order
        ]
        return ranked[:top_k]

    # Fallback: rerank disabled or reranker missing.
    final_ranks = [c.lexical_rank for c in candidates]
    _safe_publish_candidates(
        publisher,
        request_id=request_id,
        candidates=candidates,
        final_ranks=final_ranks,
        scores=[None] * len(candidates),
        model_path=None,
    )
    ranked = [
        RankedCandidate(candidate=candidate, final_rank=final_rank, score=None)
        for candidate, final_rank in zip(candidates, final_ranks, strict=True)
    ]
    ranked.sort(key=lambda item: item.final_rank)
    return ranked[:top_k]


def rrf_fuse(
    *,
    lexical_results: Sequence[tuple[str, int]],
    semantic_results: Sequence[tuple[str, int]],
    top_n: int,
    k: int = RRF_K,
) -> list[str]:
    """Reciprocal Rank Fusion over two rank lists.

    Inputs are ``(property_id, rank)`` tuples where rank is 1-based.
    """
    scores: dict[str, float] = {}
    for property_id, rank in lexical_results:
        scores[property_id] = scores.get(property_id, 0.0) + 1.0 / (k + rank)
    for property_id, rank in semantic_results:
        scores[property_id] = scores.get(property_id, 0.0) + 1.0 / (k + rank)

    sorted_ids = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [property_id for property_id, _ in sorted_ids[:top_n]]
