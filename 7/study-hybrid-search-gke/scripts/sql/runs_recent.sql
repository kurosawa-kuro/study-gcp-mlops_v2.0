-- Last 5 LightGBM LambdaRank training runs.
-- Schema reference: infra/terraform/modules/data/main.tf::training_runs.
-- (rmse / mae lived in the prior California regressor schema and are no
--  longer present.)

SELECT run_id,
       finished_at,
       metrics.ndcg_at_10,
       metrics.map,
       metrics.recall_at_20,
       model_path
FROM `mlops-dev-a.mlops.training_runs`
ORDER BY finished_at DESC
LIMIT 5
