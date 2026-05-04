"""Phase 3 — synthetic 不動産データ → PostgreSQL + Meilisearch + pgvector に投入。

CLI: ``python -m pipeline.data_job.main``

合成データ仕様 (1000 件):
- city: Tokyo / Osaka / Kyoto / Yokohama / Sapporo
- ward: city ごとに 5-10 区
- layout: 1K / 1DK / 1LDK / 2K / 2DK / 2LDK / 3LDK
- rent: 50,000 - 300,000 yen (city / layout で偏り)
- walk_min / age_years / area_m2: 適当な範囲
- pet_ok: 30% true

投入後:
- properties テーブル
- Meilisearch `properties` index (filterable: city / layout / rent / walk_min / pet_ok / age_years)
- embeddings テーブル (multilingual-e5-small で title + description を embed)
- feature_mart_property_features_daily に CTR / fav_rate / inquiry_rate の合成値を入れる
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass

import meilisearch
import psycopg
from sentence_transformers import SentenceTransformer

from ml.common import get_logger

logger = get_logger("pipeline.data_job")


CITIES = ["Tokyo", "Osaka", "Kyoto", "Yokohama", "Sapporo"]
WARDS_BY_CITY = {
    "Tokyo": ["Shibuya", "Shinjuku", "Setagaya", "Suginami", "Meguro", "Minato", "Chiyoda"],
    "Osaka": ["Chuo", "Kita", "Tennoji", "Naniwa"],
    "Kyoto": ["Sakyo", "Kamigyo", "Higashiyama"],
    "Yokohama": ["Naka", "Nishi", "Tsurumi"],
    "Sapporo": ["Chuo", "Kita", "Higashi"],
}
LAYOUTS = ["1K", "1DK", "1LDK", "2K", "2DK", "2LDK", "3LDK"]


@dataclass
class Property:
    property_id: str
    title: str
    description: str
    city: str
    ward: str
    layout: str
    rent: int
    walk_min: int
    age_years: int
    area_m2: float
    pet_ok: bool


def generate_properties(n: int = 1000, seed: int = 42) -> list[Property]:
    rng = random.Random(seed)
    out: list[Property] = []
    for i in range(n):
        city = rng.choice(CITIES)
        ward = rng.choice(WARDS_BY_CITY[city])
        layout = rng.choice(LAYOUTS)
        # rent: layout / city で増やす
        base_rent = {
            "1K": 70_000,
            "1DK": 85_000,
            "1LDK": 110_000,
            "2K": 95_000,
            "2DK": 120_000,
            "2LDK": 160_000,
            "3LDK": 220_000,
        }[layout]
        city_factor = {
            "Tokyo": 1.3,
            "Yokohama": 1.1,
            "Osaka": 1.0,
            "Kyoto": 0.9,
            "Sapporo": 0.7,
        }[city]
        rent = int(base_rent * city_factor + rng.uniform(-15_000, 15_000))
        walk_min = rng.randint(1, 25)
        age_years = rng.randint(0, 35)
        area_m2 = round(rng.uniform(15.0, 95.0), 1)
        pet_ok = rng.random() < 0.3

        title = f"{city} {ward} {layout} - {area_m2}m² 駅徒歩{walk_min}分"
        description = (
            f"{city}{ward}にある{layout}の物件。"
            f"築{age_years}年、面積{area_m2}㎡、賃料{rent:,}円、駅徒歩{walk_min}分。"
            f"{'ペット可。' if pet_ok else 'ペット不可。'}"
        )

        out.append(
            Property(
                property_id=f"prop-{i:04d}",
                title=title,
                description=description,
                city=city,
                ward=ward,
                layout=layout,
                rent=rent,
                walk_min=walk_min,
                age_years=age_years,
                area_m2=area_m2,
                pet_ok=pet_ok,
            )
        )
    return out


def _vec_literal(vec: list[float]) -> str:
    return json.dumps([float(x) for x in vec])


def insert_properties(dsn: str, props: list[Property]) -> None:
    sql = (
        "INSERT INTO properties (property_id, title, description, city, ward, layout, "
        "rent, walk_min, age_years, area_m2, pet_ok) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (property_id) DO UPDATE SET "
        "title=EXCLUDED.title, description=EXCLUDED.description, city=EXCLUDED.city, "
        "ward=EXCLUDED.ward, layout=EXCLUDED.layout, rent=EXCLUDED.rent, "
        "walk_min=EXCLUDED.walk_min, age_years=EXCLUDED.age_years, "
        "area_m2=EXCLUDED.area_m2, pet_ok=EXCLUDED.pet_ok"
    )
    rows = [
        (
            p.property_id,
            p.title,
            p.description,
            p.city,
            p.ward,
            p.layout,
            p.rent,
            p.walk_min,
            p.age_years,
            p.area_m2,
            p.pet_ok,
        )
        for p in props
    ]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)
        conn.commit()
    logger.info("inserted %d properties into PostgreSQL", len(rows))


def index_meilisearch(
    base_url: str, master_key: str, index_name: str, props: list[Property]
) -> None:
    client = meilisearch.Client(base_url, master_key)
    index = client.index(index_name)
    docs = [
        {
            "property_id": p.property_id,
            "title": p.title,
            "description": p.description,
            "city": p.city,
            "ward": p.ward,
            "layout": p.layout,
            "rent": p.rent,
            "walk_min": p.walk_min,
            "age_years": p.age_years,
            "area_m2": p.area_m2,
            "pet_ok": p.pet_ok,
        }
        for p in props
    ]
    index.update_filterable_attributes(
        ["city", "ward", "layout", "rent", "walk_min", "age_years", "pet_ok"]
    )
    index.update_searchable_attributes(["title", "description", "city", "ward", "layout"])
    task = index.add_documents(docs, primary_key="property_id")
    logger.info("Meilisearch add_documents queued: taskUid=%s docs=%d", task.task_uid, len(docs))


def embed_and_insert(
    dsn: str,
    props: list[Property],
    model_name: str,
) -> None:
    model = SentenceTransformer(model_name)
    texts = [f"passage: {p.title} {p.description}" for p in props]
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32)

    sql = (
        "INSERT INTO embeddings (property_id, embedding, model_name) "
        "VALUES (%s, %s::vector, %s) "
        "ON CONFLICT (property_id) DO UPDATE SET "
        "embedding=EXCLUDED.embedding, model_name=EXCLUDED.model_name, created_at=NOW()"
    )
    rows = [
        (p.property_id, _vec_literal(list(v)), model_name) for p, v in zip(props, vecs, strict=True)
    ]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)
        conn.commit()
    logger.info("inserted %d embeddings (model=%s)", len(rows), model_name)


def insert_feature_mart(dsn: str, props: list[Property], seed: int = 42) -> None:
    rng = random.Random(seed)
    sql = (
        "INSERT INTO feature_mart_property_features_daily "
        "(property_id, ctr, fav_rate, inquiry_rate) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (property_id) DO UPDATE SET "
        "ctr=EXCLUDED.ctr, fav_rate=EXCLUDED.fav_rate, inquiry_rate=EXCLUDED.inquiry_rate"
    )
    rows = [
        (
            p.property_id,
            round(rng.uniform(0.0, 0.18), 4),
            round(rng.uniform(0.0, 0.05), 4),
            round(rng.uniform(0.0, 0.03), 4),
        )
        for p in props
    ]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)
        conn.commit()
    logger.info("inserted feature_mart rows for %d properties", len(rows))


def main() -> None:
    dsn = os.environ.get("POSTGRES_DSN", "postgresql://admin:password@postgres:5432/hybrid_search")
    meili_url = os.environ.get("MEILI_BASE_URL", "http://meilisearch:7700")
    meili_key = os.environ.get("MEILI_MASTER_KEY", "")
    model_name = os.environ.get("E5_MODEL_NAME", "intfloat/multilingual-e5-small")

    logger.info("Phase 3 data_job start: dsn=%s meili=%s e5=%s", dsn, meili_url, model_name)

    props = generate_properties(n=1000, seed=42)
    insert_properties(dsn, props)
    index_meilisearch(meili_url, meili_key, "properties", props)
    embed_and_insert(dsn, props, model_name)
    insert_feature_mart(dsn, props, seed=42)

    logger.info("Phase 3 data_job done: %d properties seeded.", len(props))


if __name__ == "__main__":
    main()
