-- Phase 3 (Local hybrid search) DDL.
-- 起動時に postgres image の /docker-entrypoint-initdb.d/ から自動実行される。
-- 中核 5 要素 (Meilisearch BM25 + ME5 + pgvector + RRF + LightGBM LambdaRank) のうち
-- pgvector / properties / feature_mart / ranking_log / feedback_events を担う。

CREATE EXTENSION IF NOT EXISTS vector;

-- 不動産マスタ (Meilisearch / pgvector の正本)。
CREATE TABLE IF NOT EXISTS properties (
    property_id   TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL,
    city          TEXT NOT NULL,
    ward          TEXT,
    layout        TEXT NOT NULL,
    rent          INTEGER NOT NULL,
    walk_min      INTEGER NOT NULL,
    age_years     INTEGER NOT NULL,
    area_m2       REAL NOT NULL,
    pet_ok        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS properties_city_idx ON properties (city);
CREATE INDEX IF NOT EXISTS properties_rent_idx ON properties (rent);

-- ME5 embedding (semantic vector store)。
-- vector(384) は intfloat/multilingual-e5-small に合わせる。base に変える場合は 768 に migration を分岐。
CREATE TABLE IF NOT EXISTS embeddings (
    property_id   TEXT PRIMARY KEY REFERENCES properties (property_id) ON DELETE CASCADE,
    embedding     vector(384) NOT NULL,
    model_name    TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 大量データになるまで HNSW は貼らない (seq scan のほうが速い)。
-- Wave 4 で `CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops);` を計測。

-- Phase 5+ Feature Online Store の入力源相当 (Phase 4 = BQ feature_mart に相当)。
CREATE TABLE IF NOT EXISTS feature_mart_property_features_daily (
    property_id    TEXT PRIMARY KEY REFERENCES properties (property_id) ON DELETE CASCADE,
    ctr            REAL,
    fav_rate       REAL,
    inquiry_rate   REAL,
    snapshot_date  DATE NOT NULL DEFAULT CURRENT_DATE
);

-- /search ごとに 1 row (実際は候補ごとに 1 row、JSONB で展開)。
-- LambdaRank の学習データ source。Phase 4 では BQ ranking_log 相当。
CREATE TABLE IF NOT EXISTS ranking_log (
    id              BIGSERIAL PRIMARY KEY,
    request_id      TEXT NOT NULL,
    property_id     TEXT NOT NULL,
    lexical_rank    INTEGER,
    semantic_rank   INTEGER,
    me5_score       REAL,
    final_rank      INTEGER NOT NULL,
    score           REAL,
    model_path      TEXT,
    property_features JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ranking_log_request_idx ON ranking_log (request_id);
CREATE INDEX IF NOT EXISTS ranking_log_created_idx ON ranking_log (created_at);

-- /feedback で受け取る行動ログ (click / favorite / inquiry)。
-- Phase 4 では Pub/Sub → BQ feedback_events に置換される。
CREATE TABLE IF NOT EXISTS feedback_events (
    id            BIGSERIAL PRIMARY KEY,
    request_id    TEXT NOT NULL,
    property_id   TEXT NOT NULL,
    action        TEXT NOT NULL CHECK (action IN ('click', 'favorite', 'inquiry')),
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (request_id, property_id, action)
);

CREATE INDEX IF NOT EXISTS feedback_events_request_idx ON feedback_events (request_id);
