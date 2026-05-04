# ADR 0005 — Phase 7 で Deployment env は manifest 側で管理し Terraform は touch しない

**Status**: Accepted
**Phase**: Phase 6 起点 → Phase 7 で構造化

## Context

Phase 4-6 では Cloud Run Service の env を Terraform `google_cloud_run_v2_service` 内に直書き
していた。Phase 7 で `search-api` を GKE Deployment に移し、Terraform で Deployment の env も
管理しようとすると次の問題が発生:

- Phase 7 PDCA loop で `kubectl set image` / `kubectl set env` を試行錯誤すると、次の
  `terraform apply` が env を Terraform 側の値で上書きしてしまう (drift reconcile)
- env を `lifecycle.ignore_changes = [spec.template.spec.containers[*].env]` で守ると、
  Terraform から env を一切変更できなくなり、デプロイ用の `kubectl` 操作と二重管理になる

## Decision

- **Terraform 側は cluster + namespace + KServe Helm chart のみ管理**。Deployment / Service /
  HPA / Gateway / NetworkPolicy / IAP policy / SecretStore / ExternalSecret は
  `infra/manifests/` の YAML に閉じ込めて `make apply-manifests` (= `kubectl apply -k`) で配布
- Deployment env は manifest 側で literal 指定 + ConfigMap (`infra/manifests/search-api/configmap.example.yaml`、
  Run 3 で `scripts/ci/sync_configmap.py` が `env/config/setting.yaml` から自動生成) で
  非機密値を注入、Secret Manager 由来は ESO (`SecretStore` + `ExternalSecret`) で同期
- Terraform / manifests の境界は `tests/integration/infra/test_manifests_structure.py` と
  `test_terraform_module_structure.py` の 2 種類で別々に pin

## Consequences

- 1 コミットで「インフラと配備」を atomic 変更できなくなる (Terraform PR + manifest PR が
  順序問題になる) — ただし Phase 6 まで Cloud Run でやっていたときに比べて drift 事故が減る
- ESO 用 SA (`sa-external-secrets`) を 1 つ追加する分、`iam` module は膨らむ
- Phase 8 以降で「Terraform で Deployment まで管理したい」と判断するなら本 ADR を Superseded
  扱いにし、後継 ADR で全面 Terraform 化を選ぶ
