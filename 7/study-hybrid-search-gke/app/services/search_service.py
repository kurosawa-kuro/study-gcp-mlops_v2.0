"""``SearchService`` — orchestrates /search retrieval.

Pure-logic service depending only on Ports. The HTTP layer
(`app/api/routers/search_router.py`) builds a :class:`SearchInput` from
the FastAPI request, delegates to ``SearchService.search``, then maps the
returned :class:`SearchOutput` back to a Pydantic response.

Phase D-1 lifted the orchestration that was inlined in
``app/main.py:481-591`` into this class. The pure orchestration
``run_search`` from ``app/services/ranking.py`` is reused here.
"""

from __future__ import annotations

from app.domain.candidate import RankedCandidate
from app.domain.search import SearchFilters, SearchInput, SearchOutput, SearchResultItem
from app.services.protocols.candidate_retriever import CandidateRetriever
from app.services.protocols.encoder_client import EncoderClient
from app.services.protocols.feature_fetcher import FeatureFetcher
from app.services.protocols.popularity_scorer import PopularityScorer
from app.services.protocols.ranking_log_publisher import RankingLogPublisher
from app.services.protocols.reranker_client import RerankerClient
from app.services.ranking import run_search
from ml.common.logging import get_logger

logger = get_logger("app.search_service")


class SearchServiceUnavailable(Exception):
    """Raised when the SearchService cannot fulfill a request because a
    required port (encoder, retriever) is unavailable. The HTTP layer
    converts to 503.
    """


class SearchService:
    """Hybrid-search use case (inbound port equivalent).

    All collaborators are injected — composition root constructs the
    service once at startup. ``reranker`` and ``popularity_scorer`` are
    optional; ``None`` means the corresponding feature is disabled.
    """

    def __init__(
        self,
        *,
        retriever_default: CandidateRetriever | None,
        encoder: EncoderClient | None,
        publisher: RankingLogPublisher,
        reranker: RerankerClient | None = None,
        popularity_scorer: PopularityScorer | None = None,
        feature_fetcher: FeatureFetcher | None = None,
    ) -> None:
        self._retriever_default = retriever_default
        self._encoder = encoder
        self._publisher = publisher
        self._reranker = reranker
        self._popularity_scorer = popularity_scorer
        # Phase 7 PR-4 — opt-in fresh feature fetch (e.g. Vertex AI Feature
        # Online Store). ``None`` preserves Phase 5 / 6 behaviour exactly.
        self._feature_fetcher = feature_fetcher

    @property
    def reranker_model_path(self) -> str | None:
        return getattr(self._reranker, "model_path", None)

    def search(self, *, request_id: str, input: SearchInput) -> SearchOutput:
        """Execute one /search call.

        Raises :class:`SearchServiceUnavailable` when the lexical retriever
        or the encoder is missing — the HTTP handler maps to 503.
        """
        retriever = self._retriever_default
        if retriever is None:
            raise SearchServiceUnavailable("/search unavailable (retriever not configured)")
        if self._encoder is None:
            raise SearchServiceUnavailable(
                "/search disabled (enable_search=False or encoder missing)"
            )

        query_vector = self._encoder.embed(input.query, "query")
        ranked: list[RankedCandidate] = run_search(
            retriever=retriever,
            publisher=self._publisher,
            request_id=request_id,
            query_text=input.query,
            query_vector=query_vector,
            filters=input.filters,
            top_k=input.top_k,
            reranker=self._reranker,
            model_path=self.reranker_model_path,
            want_explanations=input.explain,
            feature_fetcher=self._feature_fetcher,
        )

        # Phase 6 T1 — BQML auxiliary popularity scoring (opt-in).
        popularity_map: dict[str, float] = {}
        if self._popularity_scorer is not None and ranked:
            try:
                popularity_map = self._popularity_scorer.score(
                    [item.candidate.property_id for item in ranked]
                )
            except Exception:
                logger.exception("BQML popularity scorer failed — continuing")

        items = [
            SearchResultItem(
                property_id=item.candidate.property_id,
                final_rank=item.final_rank,
                lexical_rank=item.candidate.lexical_rank,
                semantic_rank=item.candidate.semantic_rank,
                me5_score=item.candidate.me5_score,
                score=item.score,
                attributions=item.attributions,
                popularity_score=popularity_map.get(item.candidate.property_id),
                # Display-side fields (Phase 7 Run 6): copied from the candidate's
                # property_features dict that the BQ retriever populated via
                # JOIN on `properties_cleaned`. Keys may be absent under fake
                # retrievers / older callers — use `.get()` with None default.
                title=_as_str(item.candidate.property_features.get("title")),
                city=_as_str(item.candidate.property_features.get("city")),
                ward=_as_str(item.candidate.property_features.get("ward")),
                layout=_as_str(item.candidate.property_features.get("layout")),
                rent=_as_int(item.candidate.property_features.get("rent")),
                walk_min=_as_int(item.candidate.property_features.get("walk_min")),
                age_years=_as_int(item.candidate.property_features.get("age_years")),
                area_m2=_as_float(item.candidate.property_features.get("area_m2")),
                pet_ok=_as_bool(item.candidate.property_features.get("pet_ok")),
            )
            for item in ranked
        ]
        model_path = self.reranker_model_path

        return SearchOutput(
            request_id=request_id,
            items=items,
            model_path=model_path,
            ranked=ranked,
        )


# ----------------------------------------------------------------------- helpers


def _as_str(value: object) -> str | None:
    """Coerce a candidate's property_features value to ``str | None``."""
    if value is None:
        return None
    coerced = str(value).strip()
    return coerced or None


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, str, bytes, bytearray)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str, bytes, bytearray)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _as_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "y", "t"}:
            return True
        if v in {"false", "0", "no", "n", "f"}:
            return False
    return None


def filters_from_dict(raw: dict[str, object]) -> SearchFilters:
    """Coerce a Pydantic ``model_dump()`` dict to ``SearchFilters`` TypedDict.

    TypedDict has no runtime enforcement, but explicit construction keeps
    Mypy happy and surfaces unexpected keys.
    """
    out: SearchFilters = {}
    max_rent = raw.get("max_rent")
    if isinstance(max_rent, int):
        out["max_rent"] = max_rent
    layout = raw.get("layout")
    if isinstance(layout, str):
        out["layout"] = layout
    max_walk_min = raw.get("max_walk_min")
    if isinstance(max_walk_min, int):
        out["max_walk_min"] = max_walk_min
    pet_ok = raw.get("pet_ok")
    if isinstance(pet_ok, bool):
        out["pet_ok"] = pet_ok
    max_age = raw.get("max_age")
    if isinstance(max_age, int):
        out["max_age"] = max_age
    return out
