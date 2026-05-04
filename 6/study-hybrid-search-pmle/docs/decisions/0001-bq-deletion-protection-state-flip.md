# ADR 0001 — BQ table の `deletion_protection=true` を `terraform destroy` 前に state-flip する

**Status**: Accepted
**Phase**: Phase 4 起点 → Phase 5 / 6 / 7 継承

## Context

`infra/terraform/modules/data/main.tf` の BQ table 群は production 事故 (誤 destroy) を防ぐため
`deletion_protection = true` を default としている。一方、Phase 4-7 の PDCA loop は
`make destroy-all` → `make deploy-all` の 2-shot 再構築を前提にしており、`destroy-all` を実行する
たびに `deletion_protection` が立っているため `terraform destroy` がブロックされる。

Terraform 側で `deletion_protection = false` にハードコードすると本番事故に対する garde が外れる。

## Decision

- Terraform 側は `enable_deletion_protection` 変数 (default `true`) を介して flip 可能にする
- `scripts/setup/destroy_all.py` 冒頭で `PROTECTED_TABLE_TARGETS` (現状 10 table) を
  `-target` で囲んだ `terraform apply -var=enable_deletion_protection=false` を **先に**
  実行し、protection を解除した state に到達してから本体の `terraform destroy` を走らせる
- `tests/integration/infra/test_destroy_all_table_parity.py` が `destroy_all.py` の
  `PROTECTED_TABLE_TARGETS` と `infra/terraform/modules/data/main.tf` の table 列挙を
  lockstep でチェック

## Consequences

- `destroy-all` の所要時間が +1 stage 分増える (state-flip apply は数秒)
- 新規 protected table を追加するときは Python list と TF 列挙の **両方**を更新する必要がある
  (parity test が忘れた側で fail する)
- 本番 / staging で `enable_deletion_protection=true` のままにする運用は dev project と分岐
