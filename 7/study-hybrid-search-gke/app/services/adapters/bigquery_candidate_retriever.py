"""``CandidateRetriever`` adapter — Phase 7 canonical hybrid retrieval.

Lexical (Meilisearch) + semantic (Vertex AI Vector Search) → RRF fusion →
property feature enrichment via BigQuery joins on ``properties_cleaned`` +
``property_features_daily``.

Note: BigQuery is the source of truth for property + feature tables but
**not** for the semantic ANN lane — that runs through Vertex Vector Search
(see ``app/services/adapters/vertex_vector_search_semantic_search.py``).
The ``semantic`` Port is therefore required.
"""

from __future__ import annotations

from google.cloud import bigquery

from app.domain.candidate import Candidate
from app.domain.search import SearchFilters
from app.services.protocols.lexical_search import LexicalSearchPort
from app.services.protocols.semantic_search import SemanticSearchPort
from app.services.ranking import RRF_K, rrf_fuse


class BigQueryCandidateRetriever:
    """Hybrid candidate generation via lexical + semantic retrieval.

    Args:
        project_id: GCP project.
        lexical: lexical search adapter (Meilisearch).
        semantic: Vertex Vector Search adapter (canonical Phase 7 path).
        embeddings_table: fully-qualified ``project.dataset.table`` for
            ``feature_mart.property_embeddings`` — kept as the embedding
            source of truth (Vertex Vector Search index is rebuilt from it).
        features_table: ``property_features_daily`` fully-qualified name
            (for ctr / fav_rate / inquiry_rate enrichment).
        properties_table: ``feature_mart.properties_cleaned`` for rent /
            walk_min / age_years / area_m2 / pet_ok / layout filter columns.
        client: optional pre-built BQ client (tests / centralized lifecycle).
    """

    def __init__(
        self,
        *,
        project_id: str,
        lexical: LexicalSearchPort,
        semantic: SemanticSearchPort,
        embeddings_table: str,
        features_table: str,
        properties_table: str,
        client: bigquery.Client | None = None,
    ) -> None:
        self._lexical = lexical
        self._embeddings_table = embeddings_table
        self._features_table = features_table
        self._properties_table = properties_table
        self._client = client or bigquery.Client(project=project_id)
        self._semantic = semantic

    def retrieve(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        filters: SearchFilters,
        top_k: int,
    ) -> list[Candidate]:
        lexical_results = self._lexical.search(query=query_text, filters=filters, top_k=200)
        semantic_results = self._semantic.search(
            query_vector=query_vector, filters=filters, top_k=200
        )

        semantic_rank_pairs: list[tuple[str, int]] = [
            (result.property_id, result.rank) for result in semantic_results
        ]
        fused_ids = rrf_fuse(
            lexical_results=lexical_results,
            semantic_results=semantic_rank_pairs,
            top_n=max(top_k, 100),
            k=RRF_K,
        )
        if not fused_ids:
            return []

        lexical_rank_map = {result.property_id: result.rank for result in lexical_results}
        semantic_rank_map = {result.property_id: result.rank for result in semantic_results}
        me5_score_map = {result.property_id: result.similarity for result in semantic_results}
        rrf_rank_map = {pid: rank for rank, pid in enumerate(fused_ids, start=1)}

        return self._enrich_from_bq(
            property_ids=fused_ids,
            lexical_rank_map=lexical_rank_map,
            semantic_rank_map=semantic_rank_map,
            me5_score_map=me5_score_map,
            rrf_rank_map=rrf_rank_map,
        )

    def _enrich_from_bq(
        self,
        *,
        property_ids: list[str],
        lexical_rank_map: dict[str, int],
        semantic_rank_map: dict[str, int],
        me5_score_map: dict[str, float],
        rrf_rank_map: dict[str, int],
    ) -> list[Candidate]:
        query = f"""
            WITH selected AS (
              SELECT property_id, offset + 1 AS rrf_rank
              FROM UNNEST(@property_ids) AS property_id WITH OFFSET
            )
            SELECT
              s.property_id,
              s.rrf_rank,
              p.title AS p_title,
              p.city AS p_city,
              p.ward AS p_ward,
              p.layout AS p_layout,
              p.pet_ok AS p_pet_ok,
              p.rent AS p_rent,
              p.walk_min AS p_walk_min,
              p.age_years AS p_age_years,
              p.area_m2 AS p_area_m2,
              f.ctr AS f_ctr,
              f.fav_rate AS f_fav_rate,
              f.inquiry_rate AS f_inquiry_rate
            FROM selected s
            LEFT JOIN `{self._properties_table}` p USING (property_id)
            LEFT JOIN (
              SELECT *
              FROM `{self._features_table}`
              WHERE event_date = (SELECT MAX(event_date) FROM `{self._features_table}`)
            ) f USING (property_id)
            ORDER BY s.rrf_rank ASC
        """
        params = [bigquery.ArrayQueryParameter("property_ids", "STRING", property_ids)]
        rows = self._client.query(
            query,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()

        candidates: list[Candidate] = []
        for row in rows:
            property_id = str(row["property_id"])
            lexical_rank = lexical_rank_map.get(property_id, 10_000)
            semantic_rank = semantic_rank_map.get(property_id, 10_000)
            me5_score = me5_score_map.get(property_id, 0.0)
            candidates.append(
                Candidate(
                    property_id=property_id,
                    lexical_rank=lexical_rank,
                    semantic_rank=semantic_rank,
                    me5_score=me5_score,
                    property_features={
                        "rent": row["p_rent"],
                        "walk_min": row["p_walk_min"],
                        "age_years": row["p_age_years"],
                        "area_m2": row["p_area_m2"],
                        "ctr": row["f_ctr"],
                        "fav_rate": row["f_fav_rate"],
                        "inquiry_rate": row["f_inquiry_rate"],
                        "rrf_rank": rrf_rank_map.get(property_id),
                        # Display-side fields (additive — UI / response decoration only,
                        # not consumed by ranker_features.build_ranker_features).
                        # Phase 7 Run 6 で /search response に物件メタを含めるため
                        # JOIN 結果から拾い上げる。FEATURE_COLS_RANKER 10 列の parity
                        # invariant には影響しない (build_ranker_features は keys を
                        # whitelist で読むため余分な key は無視される)。
                        "title": row["p_title"],
                        "city": row["p_city"],
                        "ward": row["p_ward"],
                        "layout": row["p_layout"],
                        "pet_ok": row["p_pet_ok"],
                    },
                )
            )
        candidates.sort(key=lambda c: rrf_rank_map.get(c.property_id, 10_000))
        return candidates
