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
from app.services.protocols.ranking_log_publisher import RankingLogPublisher
from app.services.protocols.reranker_client import RerankerClient
from app.services.protocols.search_cache import SearchCachePort
from app.services.protocols.synonym_expander import SynonymExpanderPort
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
    service once at startup. ``reranker`` and ``feature_fetcher`` are
    optional; ``None`` means the corresponding feature is disabled.

    Phase 3 改修: ``popularity_scorer`` (BQML 専用) は Phase 6 / 7 の責務として除外。
    """

    def __init__(
        self,
        *,
        retriever_default: CandidateRetriever | None,
        encoder: EncoderClient | None,
        publisher: RankingLogPublisher,
        reranker: RerankerClient | None = None,
        feature_fetcher: FeatureFetcher | None = None,
        synonym_expander: SynonymExpanderPort | None = None,
        search_cache: SearchCachePort | None = None,
    ) -> None:
        self._retriever_default = retriever_default
        self._encoder = encoder
        self._publisher = publisher
        self._reranker = reranker
        # Phase 3: Postgres feature_mart_property_features_daily を直接 SELECT する
        # ``PostgresFeatureFetcher`` を渡す想定。``None`` で disabled。
        self._feature_fetcher = feature_fetcher
        # Phase 3 SYN-1: Redis 同義語辞書による lexical query expansion (Phase 7
        # SYN-1 と同型 Port)。``None`` で query_text は素通し (= Wave 1-4 既定挙動)。
        self._synonym_expander = synonym_expander
        # Phase 3 SYN-2: Redis レスポンスキャッシュ (UX/latency)。HIT は
        # encoder/retriever/reranker を全て skip し、ranking_log の publish も
        # 同条件は元 MISS で済んでいるため重複を避けて skip する。``None`` で
        # キャッシュ無効 (毎回 MISS = live search)。
        self._search_cache = search_cache

    @property
    def reranker_model_path(self) -> str | None:
        return getattr(self._reranker, "model_path", None)

    def search(self, *, request_id: str, input: SearchInput) -> SearchOutput:
        """Execute one /search call.

        Raises :class:`SearchServiceUnavailable` when the lexical retriever
        or the encoder is missing — the HTTP handler maps to 503.

        Phase 3 SYN-2 — cache short-circuit:

        - Lookup ``self._search_cache`` first; on HIT, return immediately
          with ``request_id`` overridden to the live one. The encoder /
          retriever / reranker / publisher are all skipped (the original
          MISS already published ``ranking_log``).
        - On MISS, run the full pipeline; the resulting ``SearchOutput``
          is written back into the cache before returning.

        Cache failures (``get`` / ``set`` raising) are swallowed by the
        adapter and surface as MISS / no-op respectively, so /search
        availability is not affected.
        """
        retriever = self._retriever_default
        if retriever is None:
            raise SearchServiceUnavailable("/search unavailable (retriever not configured)")
        if self._encoder is None:
            raise SearchServiceUnavailable(
                "/search disabled (enable_search=False or encoder missing)"
            )

        # Phase 3 SYN-2 — cache lookup. HIT short-circuits the rest of /search.
        if self._search_cache is not None:
            cached = self._search_cache.get(input)
            if cached is not None:
                logger.debug("/search cache HIT for request_id=%s", request_id)
                return SearchOutput(
                    request_id=request_id,
                    items=cached.items,
                    model_path=cached.model_path,
                    ranked=cached.ranked,
                )

        # Encoder runs on the original query — multilingual-e5 already
        # captures synonymy, expansion would dilute the embedding.
        query_vector = self._encoder.embed(input.query, "query")
        # Lexical side gets the expanded query when a synonym backend is
        # wired; falls back to the original query if expander is None or
        # the backend errors (RedisSynonymExpander swallows failures).
        lexical_query = (
            self._synonym_expander.expand(input.query)
            if self._synonym_expander is not None
            else input.query
        )
        ranked: list[RankedCandidate] = run_search(
            retriever=retriever,
            publisher=self._publisher,
            request_id=request_id,
            query_text=lexical_query,
            query_vector=query_vector,
            filters=input.filters,
            top_k=input.top_k,
            reranker=self._reranker,
            model_path=self.reranker_model_path,
            want_explanations=input.explain,
            feature_fetcher=self._feature_fetcher,
        )

        # Phase 3: BQML popularity scorer は除外 (Phase 6 / 7 の責務)。
        # SearchResultItem.popularity_score は常に None。
        items = [
            SearchResultItem(
                property_id=item.candidate.property_id,
                final_rank=item.final_rank,
                lexical_rank=item.candidate.lexical_rank,
                semantic_rank=item.candidate.semantic_rank,
                me5_score=item.candidate.me5_score,
                score=item.score,
                attributions=item.attributions,
                popularity_score=None,
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

        output = SearchOutput(
            request_id=request_id,
            items=items,
            model_path=model_path,
            ranked=ranked,
        )

        # Phase 3 SYN-2 — write-through. Failures in the cache adapter are
        # swallowed; subsequent identical queries simply MISS until the
        # backend recovers.
        if self._search_cache is not None:
            self._search_cache.set(input, output)

        return output


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
