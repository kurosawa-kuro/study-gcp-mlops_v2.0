# K8s manifests (Phase 7)

`infra/terraform/modules/{gke,kserve}` が作ったクラスタに、アプリケーション
層（`search-api` + KServe `InferenceService`）を `kubectl apply -k .` で
展開する。Terraform は cluster + KServe Operator + cert-manager + 3 KSA まで
面倒を見るが、個別ワークロードは manifests でバージョン管理する（CI での
ロールバック容易性のため）。

## ディレクトリ

- `search-api/` — FastAPI サービス (Deployment / Service / HPA / Gateway / PodMonitoring / ConfigMap サンプル / SecretStore / ExternalSecret)
- `kserve/` — KServe InferenceService (encoder / reranker / reranker-explain) + PodMonitoring
- `policies/` — namespace 境界ポリシー (`search-api` IAP / search namespace egress / kserve-inference ingress)
- `kustomization.yaml` — 全リソースを一括 apply する Kustomize root

## デプロイ

```bash
# 1. 事前に Terraform apply で cluster + KServe Operator を作る
cd infra/terraform/environments/dev && terraform apply

# 2. kubeconfig 取得
gcloud container clusters get-credentials hybrid-search \
  --region asia-northeast1 --project mlops-dev-a

# 3. manifests 一式を apply
make apply-manifests

# 4. encoder / reranker モデルは Vertex Model Registry から同期
uv run python scripts/deploy/kserve_models.py

# 5. search-api イメージは scripts/deploy/api_gke.py で差し替え
uv run python scripts/deploy/api_gke.py
```

`deploy-all` は manifest apply をあえて内包しない。KServe / Gateway / policy の試行錯誤をしやすくするため、Terraform apply 後に `make apply-manifests` を明示的に叩く運用を正とする。

## overlay が必要な箇所

- `search-api/gateway.yaml` の `hostname` (実際の DNS 名)
- `search-api/gateway.yaml` の `tls.certificateRefs` (`search-api-tls` Secret を参照。現状は Google-managed cert 自動化ではなく、Secret 配備または環境 overlay 前提)
- `policies/search-api-iap-policy.yaml` の `spec.default.iap.clientID` (IAP OAuth client ID を環境ごとに置換)
- `search-api/configmap.example.yaml` の `meili_base_url` (Meilisearch の Cloud Run URL)
- `kserve/encoder.yaml` / `kserve/reranker.yaml` の `storageUri` / `image`
  (scripts/deploy/kserve_models.py が自動更新)
