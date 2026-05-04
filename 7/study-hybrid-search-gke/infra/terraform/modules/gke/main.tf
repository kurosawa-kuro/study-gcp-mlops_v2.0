# =========================================================================
# GKE Autopilot cluster — hybrid-search serving layer
#
# Phase 6 の serving 層 (search-api + encoder / reranker の KServe InferenceService)
# を収容する唯一の GKE クラスタ。Autopilot を採用して node-pool 管理を持たない。
# Gateway API は Autopilot 1.29+ で既定有効、Workload Identity も既定。
# =========================================================================

resource "google_container_cluster" "hybrid_search" {
  name                = var.cluster_name
  location            = var.region
  enable_autopilot    = true
  deletion_protection = var.deletion_protection

  release_channel {
    channel = var.release_channel
  }

  # Autopilot では workload_identity_config は常に有効化され、project-level
  # `PROJECT.svc.id.goog` が使われる。明示記述で意図を残す。
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Gateway API (v1) を有効化。KServe の InferenceService から HTTPRoute を
  # 引き回す前提。
  gateway_api_config {
    channel = "CHANNEL_STANDARD"
  }

  # Autopilot が自動で管理するため、node_config / node_pool 系は宣言しない。

  lifecycle {
    ignore_changes = [
      # Autopilot 側が自動更新するフィールドは Terraform から差し戻さない
      node_pool_auto_config,
      node_pool_defaults,
    ]
  }
}

# =========================================================================
# Workload Identity bindings — GSA (Phase 5 継承) ↔ KSA (GKE 側)
#
# Phase 5 の 3 SA (sa-api / sa-endpoint-encoder / sa-endpoint-reranker) を
# そのまま使い回すため、各 GSA に対して対応 KSA からの
# workloadIdentityUser を付与する。
# =========================================================================

locals {
  wi_principal = "${var.project_id}.svc.id.goog"
}

resource "google_service_account_iam_member" "api_wi" {
  service_account_id = var.service_accounts.api.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${local.wi_principal}[${var.namespaces.search}/${var.ksa_names.api}]"
}

resource "google_service_account_iam_member" "encoder_wi" {
  service_account_id = var.service_accounts.endpoint_encoder.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${local.wi_principal}[${var.namespaces.inference}/${var.ksa_names.encoder}]"
}

resource "google_service_account_iam_member" "reranker_wi" {
  service_account_id = var.service_accounts.endpoint_reranker.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${local.wi_principal}[${var.namespaces.inference}/${var.ksa_names.reranker}]"
}

resource "google_service_account_iam_member" "external_secrets_wi" {
  service_account_id = var.service_accounts.external_secrets.name
  role               = "roles/iam.workloadIdentityUser"
  member = "serviceAccount:${local.wi_principal}[${var.namespaces.external_secrets}/${var.ksa_names.external_secrets}]"
}
