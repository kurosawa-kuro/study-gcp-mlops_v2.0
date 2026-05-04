provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {}

# ----- kubernetes / helm providers for module.kserve -----
#
# Phase 7 W3 cleanup: providers now read endpoint + token from the **local
# kubeconfig** instead of `data.google_container_cluster.hybrid_search`. The
# previous data-source-based config produced
#   ``Get "http://localhost/api/v1/namespaces/...": dial tcp 127.0.0.1:80: connect: connection refused``
# during `terraform plan -refresh` because the data source ↔ provider config
# evaluation race left provider host as `https://` (empty endpoint). With
# kubeconfig-based providers there is no such race: as long as
# `gcloud container clusters get-credentials` has populated `~/.kube/config`
# (done automatically by `scripts/infra/kubectl_context.py::ensure` from
# `deploy_all` step `apply-manifests`), `terraform plan/apply` reads endpoint
# + token directly from the kubeconfig.
#
# 2 段階 apply 前提は不変:
#   1. `terraform apply -target=module.iam -target=module.data -target=module.gke`
#      で cluster を先行作成
#   2. その直後 `gcloud container clusters get-credentials hybrid-search ...`
#      で kubeconfig 注入 (deploy_all 内で自動)
#   3. 全体 apply — kubernetes/helm provider は kubeconfig を読む
#
# WIF state recovery (`scripts/setup/recover_wif.py`) で必要だった
# `TF_VAR_k8s_use_data_source=false` placeholder mode は不要になった
# (kubeconfig が無くても provider init は失敗しない、resource 操作時のみ
# kubectl API を叩く)。

provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = "gke_${var.project_id}_${var.region}_${var.gke_cluster_name}"
}

provider "helm" {
  kubernetes {
    config_path    = "~/.kube/config"
    config_context = "gke_${var.project_id}_${var.region}_${var.gke_cluster_name}"
  }
}
