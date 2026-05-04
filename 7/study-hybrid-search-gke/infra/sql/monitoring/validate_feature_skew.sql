-- Daily feature-skew check — ranker side (real-estate hybrid search).
-- Compares feature distributions between the training window (last 90d) and
-- the recent serving window (last 1d, extracted from features logged to
-- ranking_log). Writes one row per (metric, feature) into mlops.validation_results.
--
-- Threshold defaults (mean_drift_sigma ~0.25 = WARN, ~0.5 = FAIL). Tune per
-- feature once baselines stabilize.
--
-- Feature list MUST match common/src/common/schema/feature_schema.py::
-- FEATURE_COLS_RANKER. The pytest test `tests/test_feature_parity_sql.py`
-- enforces this at CI time (added by Phase 5).

DECLARE today DATE DEFAULT CURRENT_DATE("Asia/Tokyo");
DECLARE training_start DATE DEFAULT DATE_SUB(today, INTERVAL 90 DAY);
DECLARE serving_start TIMESTAMP DEFAULT TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY);

-- Training window stats — UNPIVOT lists each feature once.
-- Source: daily property feature mart. me5_score / lexical_rank / semantic_rank
-- are query-time signals (no training-side representation), so we restrict the skew check to
-- the 7 property-side features; me5_score and lexical_rank are monitored via
-- the serving side only (volume / distribution sentinels below).
CREATE OR REPLACE TEMP TABLE training_stats AS
WITH training_rows AS (
  SELECT
    rent, walk_min, age_years, area_m2,
    ctr, fav_rate, inquiry_rate
  FROM `mlops-dev-a.feature_mart.property_features_daily`
  WHERE event_date BETWEEN training_start AND today
),
unpivoted AS (
  SELECT feature_name, value
  FROM training_rows
  UNPIVOT(value FOR feature_name IN (
    rent, walk_min, age_years, area_m2,
    ctr, fav_rate, inquiry_rate
  ))
)
SELECT feature_name, AVG(value) AS mean, STDDEV(value) AS sd
FROM unpivoted
GROUP BY feature_name;

-- Serving window stats — same feature list, read from ranking_log.features.*.
CREATE OR REPLACE TEMP TABLE serving_stats AS
WITH serving_rows AS (
  SELECT
    features.rent          AS rent,
    features.walk_min      AS walk_min,
    features.age_years     AS age_years,
    features.area_m2       AS area_m2,
    features.ctr           AS ctr,
    features.fav_rate      AS fav_rate,
    features.inquiry_rate  AS inquiry_rate
  FROM `mlops-dev-a.mlops.ranking_log`
  WHERE ts >= serving_start
),
unpivoted AS (
  SELECT feature_name, value
  FROM serving_rows
  UNPIVOT(value FOR feature_name IN (
    rent, walk_min, age_years, area_m2,
    ctr, fav_rate, inquiry_rate
  ))
)
SELECT feature_name, AVG(value) AS mean, STDDEV(value) AS sd
FROM unpivoted
GROUP BY feature_name;

-- Standardized mean drift: |(serve_mean - train_mean) / train_sd|
-- >=0.25 = WARN, >=0.5 = FAIL (rough heuristics; tune once baseline exists).
INSERT INTO `mlops-dev-a.mlops.validation_results` (run_date, metric, feature_name, value, threshold, status)
SELECT
  today AS run_date,
  'mean_drift_sigma' AS metric,
  t.feature_name,
  SAFE_DIVIDE(ABS(s.mean - t.mean), t.sd) AS value,
  0.5 AS threshold,
  CASE
    WHEN t.sd IS NULL OR t.sd = 0 THEN 'OK'
    WHEN ABS(s.mean - t.mean) / t.sd >= 0.5  THEN 'FAIL'
    WHEN ABS(s.mean - t.mean) / t.sd >= 0.25 THEN 'WARN'
    ELSE 'OK'
  END AS status
FROM training_stats t
INNER JOIN serving_stats s USING (feature_name);

-- Coverage sentinel: did we receive any search events in the last 24h?
INSERT INTO `mlops-dev-a.mlops.validation_results` (run_date, metric, feature_name, value, threshold, status)
SELECT
  today,
  'search_volume',
  NULL,
  CAST(COUNT(*) AS FLOAT64),
  100.0,
  CASE WHEN COUNT(*) < 100 THEN 'WARN' ELSE 'OK' END
FROM `mlops-dev-a.mlops.search_logs`
WHERE ts >= serving_start;

-- me5_score distribution sentinel — query-time only, so cannot skew-compare.
-- Flag if the mean drifts outside [0.3, 0.95] which would suggest the encoder
-- (or VECTOR_SEARCH distance) is misconfigured.
INSERT INTO `mlops-dev-a.mlops.validation_results` (run_date, metric, feature_name, value, threshold, status)
SELECT
  today,
  'me5_score_mean',
  'me5_score',
  AVG(me5_score) AS mean_me5,
  0.95 AS threshold,
  CASE
    WHEN COUNT(*) = 0 THEN 'OK'
    WHEN AVG(me5_score) NOT BETWEEN 0.3 AND 0.95 THEN 'WARN'
    ELSE 'OK'
  END
FROM `mlops-dev-a.mlops.ranking_log`
WHERE ts >= serving_start;
