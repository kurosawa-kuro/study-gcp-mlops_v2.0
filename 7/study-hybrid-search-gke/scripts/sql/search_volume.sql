-- /search request volume in the last 24h (one row per request).
-- Sourced from search_logs (NOT ranking_log; the latter has one row per
-- candidate, ~100x larger).

SELECT COUNT(*) AS n,
       MIN(ts) AS first_ts,
       MAX(ts) AS last_ts
FROM `mlops-dev-a.mlops.search_logs`
WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
