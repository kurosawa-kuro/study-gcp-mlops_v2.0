# infra/ — Terraform (Phase 1)

責務をモジュール単位で分離。ルートは API 有効化と backend + 4 モジュールへの dispatch のみ。

## レイアウト

```
infra/
├── apis.tf           # google_project_service (15 API 有効化)
├── backend.tf        # GCS backend: gs://mlops-dev-a-tfstate (prefix "hybrid-search-cloud")
├── provider.tf       # google provider + data.google_project.current
├── variables.tf      # project_id / region / github_repo / 各種名称
├── versions.tf       # terraform >= 1.6 / google ~> 5.40
├── main.tf           # 4 モジュール呼び出し (iam → data → messaging / monitoring)
├── outputs.tf        # ルート集約 outputs (GitHub Actions vars 向け含む)
└── modules/
    ├── iam/          # Service Accounts (5 SA 分離) + WIF + 共通プロジェクト IAM
    ├── data/         # BigQuery / GCS / Artifact Registry / Secret Manager + データ IAM
    ├── messaging/    # Pub/Sub / Scheduler / BQ Subscription
    └── monitoring/   # log-based metrics / alert policies / Scheduled Query (property feature skew)
```

## 依存グラフ

```
apis.enabled
  └─▶ iam (SA / WIF / 共通 IAM)
        └─▶ data (BQ / GCS / AR / Secret + SA-data IAM)
              ├─▶ messaging (Pub/Sub / Scheduler)
              └─▶ monitoring (log metrics / alerts / skew scheduled query)
```

## 前提 (Phase 0、`make tf-bootstrap` で半自動化)

- プロジェクト `mlops-dev-a` 作成済み
- tfstate バケット `gs://mlops-dev-a-tfstate` 作成済み (uniform access + versioning)
- API 有効化済み (`serviceusage.googleapis.com` など含む 15 個、`apis.tf` が Terraform 管理で引き継ぐ)
- 適用者は Project Owner 相当

## 初回適用

```bash
cd ..
make tf-bootstrap                        # Phase 0 (冪等)
make tf-init
make tf-plan GITHUB_REPO=<owner>/<name>
terraform -chdir=infra apply
```

`docs/runbook/05_運用.md §1 STEP 7–13` で完全手順。

## 生成される主要リソース (モジュール別)

| モジュール | 主要リソース |
|---|---|
| `iam` | 5 ランタイム SA (`sa-api` / `sa-job-train` / `sa-job-embed` / `sa-dataform` / `sa-scheduler`) + `sa-github-deployer` + WIF pool + provider |
| `data` | BQ datasets (`mlops` / `feature_mart` / `predictions`) + tables (`training_runs` / `search_logs` / `ranking_log` / `feedback_events` / `validation_results` / `property_features_daily` / `property_embeddings`) + GCS (`mlops-dev-a-models` / `-artifacts`) + Artifact Registry (`mlops`) + Secret Manager (`meili-master-key`) + Dataform repository + BQ/GCS/Secret ↔ SA IAM |
| `messaging` | Pub/Sub topics (`ranking-log` / `search-feedback` / `retrain-trigger`) + BQ Subscriptions + Cloud Scheduler `check-retrain-daily` |
| `monitoring` | log-based metrics (`search_api_5xx` / `search_api_latency_ms`) + email 通知チャネル + 2 alert policies + Scheduled Query `property_feature_skew_check` |

全リソース・スキーマの逐一掲載は [`docs/architecture/03_実装カタログ.md §6`](../docs/architecture/03_実装カタログ.md)。

## モジュール間境界

- **入力**: モジュールは `project_id` / `region` などスカラー値、および上流モジュールの object 出力 (`module.iam.service_accounts`) を受け取る
- **出力**: 各モジュールの `outputs.tf` が下流で必要な最小セットを公開。ルート `outputs.tf` はそれらを GitHub Actions 向けや運用向けに整形
- `data.google_project.current` は `messaging` モジュールが Pub/Sub service agent を合成するために再宣言 (モジュール境界を越えない)

## 注意

- Secret の値は Terraform 管理外 (`gcloud secrets versions add` で投入、`docs/runbook/05_運用.md §1 STEP 10`)
- `google_dataform_repository` は IaC 管理済 (`modules/data/main.tf`、`docs/runbook/05_運用.md §1 STEP 12`)
- ルート `outputs.tf` の `workload_identity_provider` / `github_deployer_sa_email` を GitHub Actions Variables に登録 (`docs/runbook/05_運用.md §1 STEP 11`)
- `terraform validate` は `make tf-validate` で backend-less に走る (モジュール init も含む)
