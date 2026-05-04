# ADR 0008 — `module.kserve` の K8s/Helm リソースは GKE cluster より先に target destroy する

**Status**: Accepted
**Phase**: Phase 7 起点

## Context

Phase 7 の `infra/terraform/environments/dev/provider.tf` は `kubernetes` / `helm`
provider を `data.google_container_cluster.hybrid_search` の endpoint / token を
使って構成している:

```hcl
data "google_container_cluster" "hybrid_search" { ... }

provider "kubernetes" {
  host                   = "https://${data.google_container_cluster.hybrid_search.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(...)
}
```

`make destroy-all` の本体 (`terraform destroy -auto-approve`) を素直に走らせると、
Terraform は依存グラフから本来 `module.kserve` の K8s リソース → `module.gke` の
cluster の順で destroy するはずだが、実 GCP 環境では次のいずれかで fail する:

1. cluster が destroy 中 / 既消滅で `data.google_container_cluster.hybrid_search.endpoint`
   が `null` / 空文字に refresh される → provider が `http://localhost:80` に fallback
2. ローカルに kubeconfig がそろっていない / Workload Identity の token 解決に失敗
3. cert-manager の helm_release が cluster API call を伴う finalizer を持っており、
   cluster 接続性が要る

エラー例:
```
Error: Get "http://localhost/api/v1/namespaces/search": dial tcp 127.0.0.1:80: connect: connection refused
Error: Kubernetes cluster unreachable: invalid configuration: no configuration has been provided
```

## Decision

`scripts/setup/destroy_all.py` の destroy フローを **2 段階** に分ける:

1. `terraform destroy -target=module.kserve` を **先行実行** — module 単位で
   一括 target することで、個別 resource の列挙漏れを防ぐ。module 配下:
   `helm_release.{cert_manager,external_secrets,kserve_crd,kserve}` +
   `kubernetes_namespace.{search,inference}` +
   `kubernetes_service_account.{api,encoder,reranker}`
2. その後 `terraform destroy -auto-approve` で本体 (cluster 含む全リソース) を destroy

### Fallback (cluster 既消滅時)

step 1 の **exit code が 0 でも** cluster unreachable で K8s API 呼び出しが
silent skip され state に残骸が残るケースがある (Phase 7 Run 4 で
`helm_release.kserve_crd` が **個別列挙から漏れて** `0 destroyed` が返ったが
state に残存していたパターン)。よって fallback の判定は:

- (a) targeted destroy が exit 0 以外
- (b) `terraform state list` で `module.kserve.` prefix がまだ非空

のどちらかで `terraform state rm module.kserve` を実行 (module 全体の state を
一括除去)。step 2 の本体 destroy が K8s/Helm provider を起動せずに進む。

### 該当コード

- 定数: `scripts/setup/destroy_all.py::KSERVE_MODULE_TARGET = "module.kserve"` (module 単位 target)
- 後方確認 helper: `_kserve_state_remaining(infra_dir)` — `terraform state list` を
  `module.kserve.` prefix で filter して残存を返す
- ロジック: `scripts/setup/destroy_all.py::main()` の step `[5/6]` (target destroy +
  exit code / 残存 list の OR で fallback 起動) + `_state_rm_kserve_resources(infra_dir)`
  (module 単位 `state rm`)

## Consequences

- destroy フロー全体は `[1/6] seed-test-clean` → `[2/6] undeploy Vertex endpoints` →
  `[3/6] wipe GCS buckets` → `[4/6] state-flip BQ deletion_protection` →
  **`[5/6] target destroy module.kserve K8s/Helm`** → `[6/6] full destroy` の 6 段
- step 5 が +30〜60 秒程度 destroy 全体時間を増やすが、cluster 共倒れによる手動
  state 修復 (場合によっては 30 分〜) と比べれば誤差
- 新たに K8s / Helm リソースを `module.kserve` に追加した時の **メンテ負担なし** —
  `-target=module.kserve` (module 単位 target) と `terraform state rm module.kserve`
  (module 単位 state rm) で配下 resource は自動的に網羅される (Phase 7 Run 4 で
  個別列挙の取りこぼし事故を踏んだので、その教訓の上に立つ)
- 本 ADR と ADR 0005 (Deployment env を manifest 側で管理) は同じ哲学:
  **「Terraform で Kubernetes API を直接叩く設計は壊れやすい」** → manifest /
  外部スクリプトに切り出すか、destroy 順序を明示制御する。Phase 8 以降で
  `infra/manifests/` を Terraform `kubernetes_manifest` 経由に戻す判断をした場合、
  本 ADR の destroy 戦略はそのまま流用可能 (target destroy の対象 module を
  追加するだけ)
