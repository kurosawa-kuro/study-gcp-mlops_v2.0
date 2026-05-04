-- Daily self-managed drift check for Phase 7 GKE + KServe serving.
--
-- Vertex Model Monitoring v2 no longer attaches to live traffic because
-- encoder / reranker serve behind KServe, not Vertex Endpoints. As a
-- lightweight substitute, compare recent model outputs recorded in
-- `mlops.ranking_log` against a 14-day serving baseline and write drift
-- alerts into `mlops.model_monitoring_alerts`.
--
-- Scope:
-- - reranker score (`ranking_log.score`)
-- - semantic score proxy (`ranking_log.me5_score`)
--
-- This is intentionally serving-vs-serving (recent 1d vs trailing 14d),
-- not training-vs-serving. Property-side feature skew still lives in
-- `monitoring/validate_feature_skew.sql` and writes to `validation_results`.

DECLARE alert_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
DECLARE recent_start TIMESTAMP DEFAULT TIMESTAMP_SUB(alert_time, INTERVAL 1 DAY);
DECLARE baseline_start TIMESTAMP DEFAULT TIMESTAMP_SUB(alert_time, INTERVAL 15 DAY);
DECLARE baseline_end TIMESTAMP DEFAULT TIMESTAMP_SUB(alert_time, INTERVAL 1 DAY);

CREATE OR REPLACE TEMP TABLE baseline_stats AS
WITH baseline_rows AS (
  SELECT "reranker_score" AS feature_name, score AS value
  FROM `mlops-dev-a.mlops.ranking_log`
  WHERE ts >= baseline_start AND ts < baseline_end AND score IS NOT NULL

  UNION ALL

  SELECT "me5_score" AS feature_name, me5_score AS value
  FROM `mlops-dev-a.mlops.ranking_log`
  WHERE ts >= baseline_start AND ts < baseline_end AND me5_score IS NOT NULL
)
SELECT
  feature_name,
  COUNT(*) AS sample_count,
  AVG(value) AS mean_value,
  STDDEV(value) AS sd_value
FROM baseline_rows
GROUP BY feature_name;

CREATE OR REPLACE TEMP TABLE recent_stats AS
WITH recent_rows AS (
  SELECT "reranker_score" AS feature_name, score AS value
  FROM `mlops-dev-a.mlops.ranking_log`
  WHERE ts >= recent_start AND score IS NOT NULL

  UNION ALL

  SELECT "me5_score" AS feature_name, me5_score AS value
  FROM `mlops-dev-a.mlops.ranking_log`
  WHERE ts >= recent_start AND me5_score IS NOT NULL
)
SELECT
  feature_name,
  COUNT(*) AS sample_count,
  AVG(value) AS mean_value,
  STDDEV(value) AS sd_value
FROM recent_rows
GROUP BY feature_name;

INSERT INTO `mlops-dev-a.mlops.model_monitoring_alerts`
  (alert_time, model_resource_name, drift_metric, feature_name, score, threshold, payload)
SELECT
  alert_time,
  CASE recent.feature_name
    WHEN "reranker_score" THEN "kserve://property-reranker"
    WHEN "me5_score" THEN "kserve://property-encoder"
    ELSE "kserve://unknown"
  END AS model_resource_name,
  "mean_drift_sigma" AS drift_metric,
  recent.feature_name,
  SAFE_DIVIDE(ABS(recent.mean_value - baseline.mean_value), baseline.sd_value) AS score,
  0.3 AS threshold,
  TO_JSON(STRUCT(
    baseline.sample_count AS baseline_sample_count,
    recent.sample_count AS recent_sample_count,
    baseline.mean_value AS baseline_mean,
    recent.mean_value AS recent_mean,
    baseline.sd_value AS baseline_sd,
    recent.sd_value AS recent_sd,
    recent_start AS recent_window_start,
    baseline_start AS baseline_window_start,
    baseline_end AS baseline_window_end,
    CASE
      WHEN baseline.sample_count < 100 OR recent.sample_count < 30 THEN "INSUFFICIENT_DATA"
      WHEN baseline.sd_value IS NULL OR baseline.sd_value = 0 THEN "NO_BASELINE_VARIANCE"
      WHEN SAFE_DIVIDE(ABS(recent.mean_value - baseline.mean_value), baseline.sd_value) >= 0.5 THEN "FAIL"
      WHEN SAFE_DIVIDE(ABS(recent.mean_value - baseline.mean_value), baseline.sd_value) >= 0.3 THEN "WARN"
      ELSE "OK"
    END AS status
  )) AS payload
FROM baseline_stats baseline
INNER JOIN recent_stats recent USING (feature_name)
WHERE baseline.sample_count >= 100
  AND recent.sample_count >= 30;
