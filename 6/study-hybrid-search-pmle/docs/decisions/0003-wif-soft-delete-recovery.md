# ADR 0003 — WIF pool/provider の 30 日 soft-delete に対する `_recover_wif_state` 自動 undelete

**Status**: Accepted
**Phase**: Phase 4 起点 → Phase 5 / 6 / 7 継承

## Context

GCP Workload Identity Federation の pool / provider は `terraform destroy` で削除すると
**30 日 soft-delete** に入り、同名で `terraform apply` すると "name already exists / soft
deleted" エラーで失敗する。これは GCP 側の仕様で、Terraform provider は undelete を
自動でやってくれない。

PDCA dev project では `destroy-all` → `deploy-all` を頻繁に回すため、毎回 WIF が
soft-delete に入って `make deploy-all` の再構築が止まる。

## Decision

`scripts/setup/deploy_all.py::_recover_wif_state` で次を自動実行:

1. soft-deleted な WIF pool / provider を `gcloud iam workload-identity-pools undelete`
2. `terraform import` で undelete されたリソースを state に戻す
3. その後の `terraform apply` は通常進行

これにより `make destroy-all` → `make deploy-all` の cycle が WIF に阻まれず回る。

## Consequences

- `deploy-all` フローが冪等になる代わりに、`_recover_wif_state` が `gcloud` + Terraform
  state を直接触る = 一般的でない destructive operation を含む。CLAUDE.md の事前承認で
  カバー (PDCA dev project スコープに限定)
- 別 project / production には適用しない (destroy しない前提)
- 30 日経って soft-delete から完全削除されると undelete も import も失敗するので、
  そのときは手動 `terraform state rm` + 再 apply で回復する
