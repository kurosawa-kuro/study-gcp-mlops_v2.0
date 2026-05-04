-- Phase 6 T1 — BQML property-popularity model.
--
-- CREATE MODEL is a PMLE-syllabus must-know surface; running this against
-- mlops-dev-a teaches the same options (model_type / input_label_cols /
-- data_split / evaluation / HP tuning) the exam expects.
--
-- Inputs: the 7 property-side ranker features already maintained by
-- parity invariant. Output: predicted_ctr = the BQML label = next-day
-- historical CTR. Use ML.PREDICT downstream (see
-- app/services/adapters/bqml_popularity_scorer.py) to convert a property
-- into a popularity score at /search time.
--
-- Usage:
--   PROJECT_ID=mlops-dev-a make bqml-train-popularity
-- or directly:
--   bq query --use_legacy_sql=false < scripts/bqml/train_popularity.sql
--
-- Parity note: this model reads the property-side 7 columns but does NOT
-- add them to FEATURE_COLS_RANKER. Its output surfaces in
-- SearchResultItem.popularity_score; wiring it as an 11th rerank feature
-- would trigger the 6-file parity cascade and is intentionally deferred.

CREATE OR REPLACE MODEL `mlops-dev-a.mlops.property_popularity`
OPTIONS (
  model_type = 'BOOSTED_TREE_REGRESSOR',
  input_label_cols = ['ctr'],
  max_iterations = 50,
  learn_rate = 0.1,
  l2_reg = 1.0,
  min_tree_child_weight = 1,
  enable_global_explain = TRUE,
  data_split_method = 'AUTO_SPLIT'
) AS
SELECT
  p.rent,
  p.walk_min,
  p.age_years,
  p.area_m2,
  f.fav_rate,
  f.inquiry_rate,
  f.ctr
FROM `mlops-dev-a.feature_mart.properties_cleaned` p
JOIN `mlops-dev-a.feature_mart.property_features_daily` f USING (property_id)
WHERE f.event_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 28 DAY)
  AND f.ctr IS NOT NULL;
