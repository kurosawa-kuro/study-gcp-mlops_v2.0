variable "enable_composer" {
  description = "Provision the Cloud Composer (Gen 3, Managed Airflow 2.x) environment for Phase 7 canonical orchestration. Default true; cost is bounded by `make destroy-all` between PDCA cycles. DCU-hour pricing (Gen 3): ~$0.72/h (12 DCU × $0.06) ≒ ~¥115/h. Single 50-65min verify costs ~¥150-300; the real risk is destroy leak (24h leak ≒ ¥2,800, multi-day leak can reach ¥10,000+, full month always-on ≒ ¥84,000)."
  type        = bool
  default     = true
}

variable "environment_name" {
  description = "Cloud Composer environment name (shown in Cloud Console / `gcloud composer environments list`)."
  type        = string
  default     = "hybrid-search-orchestrator"
}

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "Region for the Composer environment (e.g. asia-northeast1)."
  type        = string
}

variable "vertex_location" {
  description = "Vertex AI location surfaced to DAGs via env_variables (typically equals `region`)."
  type        = string
  default     = "asia-northeast1"
}

variable "composer_service_account_email" {
  description = "GCP service account email the Composer environment runs as. Created in `module.iam.google_service_account.composer` (Phase 7 W2-4)."
  type        = string
}

variable "pipeline_root_bucket_name" {
  description = "GCS bucket name (no `gs://`) for Vertex Pipelines run artifacts. Surfaced to DAGs as PIPELINE_ROOT_BUCKET."
  type        = string
}

variable "pipeline_template_gcs_path" {
  description = "GCS path to compiled KFP pipeline YAML (e.g. `gs://<bucket>/templates/property-search-train.yaml`). DAG `retrain_orchestration` reads this to submit Vertex PipelineJob via `scripts.ops.train_now`."
  type        = string
  default     = ""
}

variable "vector_search_index_resource_name" {
  description = "Vertex AI Vector Search index resource name (`projects/.../locations/.../indexes/...`). Surfaced to DAG `daily_feature_refresh::backfill_vvs_incremental`."
  type        = string
  default     = ""
}

variable "feature_online_store_id" {
  description = "Vertex AI Feature Online Store ID. Surfaced to DAG `daily_feature_refresh::trigger_fv_sync` for Feature View sync."
  type        = string
  default     = ""
}

variable "feature_view_id" {
  description = "Vertex AI Feature View ID under the Feature Online Store."
  type        = string
  default     = ""
}

variable "api_external_url" {
  description = "Public HTTPS URL of search-api GKE Gateway. DAG `retrain_orchestration::check_retrain` POSTs `/jobs/check-retrain` to this URL as a smoke."
  type        = string
  default     = ""
}

variable "slo_availability_goal" {
  description = "Availability SLO target (fraction 0-1) surfaced to DAG `monitoring_validation::check_slo_burn_rate`."
  type        = number
  default     = 0.99
}

variable "composer_runner_image" {
  description = "V5 fix (2026-05-03、§4.1): KubernetesPodOperator が起動する `composer-runner` image URI。`make build-composer-runner` で push される `<region>-docker.pkg.dev/<project>/<repo>/composer-runner:latest` を default で参照する。`pipeline/dags/_pod.py::_composer_runner_image()` が COMPOSER_RUNNER_IMAGE env を一次参照、env 未設定時は project + region + repo から組み立てる fallback を持つ。"
  type        = string
  default     = ""
}
