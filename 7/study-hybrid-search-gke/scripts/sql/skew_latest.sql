-- Today's per-feature skew check results from validation_results.
-- Populated by monitoring/validate_feature_skew.sql via the
-- property_feature_skew_check Scheduled Query (daily 05:00 JST).

SELECT metric, feature_name, value, threshold, status
FROM `mlops-dev-a.mlops.validation_results`
WHERE run_date = CURRENT_DATE("Asia/Tokyo")
ORDER BY status DESC, ABS(value) DESC
