variable "project_id" {
  type    = string
  default = "mlops-dev-a"
}

variable "region" {
  type    = string
  default = "asia-northeast1"
}

variable "artifact_repo_id" {
  type    = string
  default = "mlops"
}

variable "models_bucket_name" {
  type    = string
  default = "mlops-dev-a-models"
}

variable "pipeline_root_bucket_name" {
  description = "GCS bucket name for Vertex AI pipeline root artifacts and compiled templates"
  type        = string
  default     = "mlops-dev-a-pipeline-root"
}

variable "meili_data_bucket_name" {
  description = "GCS bucket name mounted by meili-search"
  type        = string
  default     = "mlops-dev-a-meili-data"
}

variable "artifacts_bucket_name" {
  type    = string
  default = "mlops-dev-a-artifacts"
}

variable "github_repo" {
  description = "GitHub repository (owner/name) trusted by Workload Identity Federation + used for Dataform git_remote_settings"
  type        = string
  default     = "your-org/study-gcp-mlops-hybrid-search-cloud"
}

variable "admin_user_emails" {
  description = "Developer user account emails that need to impersonate sa-api for local one-off ops (e.g. Meilisearch document sync that requires OIDC token with audience=meili-search URL). Empty list disables the binding. Forwarded to module.iam."
  type        = list(string)
  default     = []
}

variable "dataform_repository_id" {
  description = "Dataform repository name. Must match .github/workflows/deploy-dataform.yml env.REPOSITORY"
  type        = string
  default     = "hybrid-search-cloud"
}

variable "dataform_git_token_secret_version" {
  description = "Secret Manager resource ID for the GitHub PAT Dataform uses to sync definitions/. Empty = no remote sync (use Dataform UI or CI-driven compilationResults only)"
  type        = string
  default     = ""
}

variable "oncall_email" {
  description = "Email notified by log-based alert policies. Required — must be supplied via -var='oncall_email=...' or tfvars at apply time. No default is provided on purpose (avoid shipping placeholder addresses)."
  type        = string

  validation {
    condition     = length(var.oncall_email) > 0 && can(regex("@", var.oncall_email))
    error_message = "oncall_email must be a non-empty address containing '@'."
  }
}

variable "enable_deletion_protection" {
  description = "Toggle BQ table deletion_protection across the data module. Default true (production-safe). `make destroy-all` runs `terraform apply -var=enable_deletion_protection=false` first so the subsequent destroy can proceed (Terraform refuses to destroy a table whose state still says deletion_protection=true)."
  type        = bool
  default     = true
}

variable "vertex_location" {
  description = "Vertex AI location for Pipelines / Feature Group / Model Registry (inherited from Phase 5)"
  type        = string
  default     = "asia-northeast1"
}

variable "vertex_encoder_endpoint_id" {
  description = "Vertex AI encoder endpoint ID (legacy — retained for Phase 5 compatibility; Phase 7 uses KServe)"
  type        = string
  default     = ""
}

variable "vertex_reranker_endpoint_id" {
  description = "Vertex AI reranker endpoint ID (legacy — retained for Phase 5 compatibility; Phase 7 uses KServe)"
  type        = string
  default     = ""
}

variable "enable_vertex_endpoint_shell" {
  description = "When true, create empty Vertex AI Endpoint shells for encoder/reranker. Default false because Phase 7 serves via GKE + KServe."
  type        = bool
  default     = false
}

variable "gke_cluster_name" {
  description = "GKE Autopilot cluster name for Phase 7 serving"
  type        = string
  default     = "hybrid-search"
}

## Phase 7 W3 cleanup: `k8s_use_data_source` is deprecated. The kubernetes /
## helm providers now read endpoint+token from the local kubeconfig
## (`scripts/infra/kubectl_context.py::ensure` is invoked before any K8s
## terraform op runs), removing the data-source ↔ provider-config evaluation
## race that produced ``Get "http://localhost/api/v1/namespaces/..."`` errors
## during plan/refresh. The variable was kept as ``true`` default + occasional
## ``false`` override in `recover_wif.py`; with the kubeconfig-based providers
## the override is no longer needed. **Variable removed**; provider.tf no
## longer references it.

variable "api_external_url" {
  description = "Public HTTPS URL of search-api GKE Gateway. Leave empty on initial apply; fill after Gateway has provisioned and re-apply to materialize Cloud Scheduler."
  type        = string
  default     = ""
}

# =========================================================================
# Phase 6 T5 — SLO tunables forwarded to module.slo.
# =========================================================================

variable "slo_availability_goal" {
  description = "Availability SLO target for search-api (fraction 0-1). Default 0.99; raise after burn-rate data justifies it."
  type        = number
  default     = 0.99
}

variable "slo_latency_threshold_ms" {
  description = "Latency SLO threshold (milliseconds). Requests completing under this count as 'good'. Default 500ms mirrors the existing p95 alert."
  type        = number
  default     = 500
}

variable "slo_latency_goal" {
  description = "Fraction of requests that must complete under slo_latency_threshold_ms. Default 0.95 (p95 target)."
  type        = number
  default     = 0.95
}

variable "slo_rolling_period_days" {
  description = "Rolling window for both SLOs. Default 28 days (avoids month-boundary edge cases vs 30)."
  type        = number
  default     = 28
}

# =========================================================================
# Phase 6 T2 — Dataflow streaming toggles.
# =========================================================================

variable "enable_streaming" {
  description = "Provision the Dataflow streaming module (sa-dataflow + IAM). Default false; flip to true after ranking-log has meaningful traffic."
  type        = bool
  default     = false
}

variable "enable_streaming_job" {
  description = "Actually launch the Flex Template streaming job. Requires enable_streaming=true AND streaming_flex_template_gcs_path to be non-empty (= template already built)."
  type        = bool
  default     = false
}

variable "streaming_flex_template_gcs_path" {
  description = "GCS path to the compiled Flex Template spec JSON (built out-of-band by scripts/setup/build_streaming_template.py). Empty suppresses the Dataflow job resource."
  type        = string
  default     = ""
}

# =========================================================================
# Vertex AI Feature Online Store toggle (Phase 7 — vertex_feature_group.py).
# =========================================================================

variable "enable_feature_online_store" {
  description = "Provision the Vertex AI Feature Online Store + FeatureView so feature_group.py fetches return featureValues. Default true for the dev PDCA environment; cost is bounded by `make destroy-all` between cycles. Optimized FOS rejects updates; module.vertex ignores drift on optimized/dedicated_serving_endpoint/labels. Live serving hostname for Pods comes from Vertex API in `scripts/deploy/configmap_overlay.py` when terraform output is empty."
  type        = bool
  default     = true
}

# =========================================================================
# Vertex AI Vector Search toggle (Phase 7 Wave 2 W2-1) — module "vector_search"
# が ME5 ベクトル検索の本番 serving index を provision する。embedding 履歴
# 正本は BigQuery feature_mart.property_embeddings に残る (二層構造)。
# =========================================================================

variable "enable_vector_search" {
  description = "Provision the Vertex AI Vector Search index + endpoint + deployed index. Default true for the dev PDCA environment so `make deploy-all` provisions the canonical Phase 7 semantic-search backend without TF_VAR overrides; rely on `make destroy-all` between PDCA cycles to bound replica cost."
  type        = bool
  default     = true
}

# =========================================================================
# Cloud Composer toggle (Phase 7 W2-4) — module "composer" provisions the
# canonical Managed Airflow Gen 3 environment that runs the 3 main DAGs
# (`daily_feature_refresh` / `retrain_orchestration` / `monitoring_validation`).
# Cost (Gen 3 DCU-hour 課金): Composer 単体でも常駐課金がある。Phase 7 full を
# 3h 学習セッションで回すと全体で概ね ~¥870-1,200 レンジを見込む一方、真の
# リスクは destroy leak (24h leak ≒ ~¥4,000-6,000, multi-day / monthly は
# さらに増える)。Stage 1 keeps default=false to preserve current deploy-all
# behaviour; Stage 3 flips to default=true.
# =========================================================================

variable "enable_composer" {
  description = "Provision the Cloud Composer (Gen 3) environment. Default true (Stage 3 flip 2026-05-02): Phase 7 = canonical 起点として `make deploy-all` で Composer 環境を立ち上げる本線運用。現設定の 3h 学習 1 回では full 構成全体で ~¥870-1,200 が目安 (詳細 docs/runbook/05_運用.md §1.4-bis)。`enable_composer=false` で provisioning skip も可 (Composer 不要な作業時)。"
  type        = bool
  default     = true
}

variable "composer_environment_name" {
  description = "Cloud Composer environment name (shown in Cloud Console / `gcloud composer environments list`). Single environment per dev project."
  type        = string
  default     = "hybrid-search-orchestrator"
}

variable "pipeline_template_gcs_path" {
  description = "GCS path to compiled KFP pipeline YAML (e.g. `gs://<bucket>/templates/property-search-train.yaml`). DAG `retrain_orchestration::submit_train_pipeline` reads this to invoke `scripts.ops.train_now`. Empty = DAG falls back to local compile (Stage 2 default)."
  type        = string
  default     = ""
}

variable "composer_runner_image" {
  description = "V5 fix (2026-05-03、§4.1): KubernetesPodOperator が起動する `composer-runner` image URI。`make build-composer-runner` で push される `<region>-docker.pkg.dev/<project>/<repo>/composer-runner:latest` を default で参照する。空ならば DAG 側 fallback (project + region + repo から組み立て)。"
  type        = string
  default     = ""
}

# =========================================================================
# Phase 7 SYN-1 — Redis synonym dictionary (lexical query expansion)
# =========================================================================

variable "enable_redis_synonym" {
  description = "Provision Cloud Memorystore for Redis backing the lexical synonym dictionary (SynonymExpanderPort, Phase 7 SYN-1). Default false: ``synonym_backend=none`` keeps Phase 5/6 behaviour. Flip to true to opt in; the search-api ConfigMap then consumes ``module.redis_synonym.redis_url`` via the ``configmap_overlay`` deploy step."
  type        = bool
  default     = false
}

variable "redis_synonym_vpc_network" {
  description = "VPC self-link the GKE cluster runs in (Memorystore peers via Private Service Access). Required only when ``enable_redis_synonym=true``. Example: ``projects/<project>/global/networks/default``."
  type        = string
  default     = ""
}
