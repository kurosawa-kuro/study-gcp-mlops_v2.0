# .github/workflows — Phase 7 (CI/CD)

## ジョブ一覧

| Workflow | トリガー | 役割 |
|---|---|---|
| `ci.yml` | すべての PR / push | ruff + mypy + pytest をマトリクスで並列実行 (uv) |
| `terraform.yml` | `infra/**` | plan (PR コメント) + apply (main マージ) |
| `deploy-api.yml` | `app/**` / `ml/**` | docker build → push → `gcloud run deploy search-api` |
| `deploy-trainer-image.yml` | `ml/training/**` / `ml/common/**` / `ml/data/**` / `ml/registry/**` / `ml/evaluation/**` | docker build → push (Vertex Training image) |
| `deploy-encoder-image.yml` | `ml/serving/**` / `ml/common/**` / `ml/registry/**` | docker build → push (encoder CPR image) |
| `deploy-reranker-image.yml` | `ml/serving/**` / `ml/data/feature_engineering/**` / `ml/registry/**` | docker build → push (reranker CPR image) |
| `deploy-pipeline.yml` | `pipeline/**` | KFP compile → upload + Vertex Model Monitoring/Schedule |
| `deploy-dataform.yml` | `definitions/**` | Dataform CLI compile + リポジトリ pull トリガー |

## 必須 GitHub Variables

Repository settings → Variables で設定:

| 名前 | 値 |
|---|---|
| `WORKLOAD_IDENTITY_PROVIDER` | `projects/<number>/locations/global/workloadIdentityPools/github/providers/github-oidc` (`terraform output workload_identity_provider` で取得) |
| `DEPLOYER_SERVICE_ACCOUNT` | `sa-github-deployer@mlops-dev-a.iam.gserviceaccount.com` |

## Secrets

**不要**。Workload Identity Federation を使うので SA Key は作らない。Doppler トークンは Cloud Run の環境変数経由 (Secret Manager 参照) で注入するので CI には載せない。

## 設計上の判断

- **SA Key を作らない** (`study-gcp/study-gcp-mlops` の `credentials_json: ${{ secrets.GCP_SA_KEY }}` を捨てた理由) — セキュリティポスチャ向上と、キーローテーション不要のため。
- **path filter** で `app/**` / `ml/**` / `pipeline/**` を分離 — 片方の変更で全部がデプロイされない。共通の `ml/common/**` は trainer/encoder 系の両方に含める。
- **lint/typecheck/test はマトリクス並列** — 直列だとキャッシュ温存できる代わりに待ち時間が長くなるため並列優先。uv が依存を速くインストールできる前提。
- **Cloud Run の template は `ignore_changes`** で Terraform 管轄から外し、CI が `gcloud run deploy/update` で image を更新する形にドリフト防止。
