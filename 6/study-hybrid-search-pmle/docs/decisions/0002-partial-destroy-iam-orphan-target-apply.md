# ADR 0002 — 半 destroy 後の SA / Dataset IAM orphan を `-target` で部分 apply する

**Status**: Accepted
**Phase**: Phase 4 起点 → Phase 5 / 6 / 7 継承

## Context

`make destroy-all` が **途中で失敗した状態** (例: BQ table の force-destroy timeout、
Cloud Run service の API enabled 待ち) で停止すると、tfstate と GCP 実態が乖離する。
特に SA / IAM binding は orphan のまま残ることが多く、その後 `make deploy-all` (= 純粋
`terraform apply`) を打つと "already exists / cannot create" のエラーで進まなくなる。

普通に `terraform apply` を打つと全 module を network 単位で再評価しに行き、orphan を
拾うために多数の `import` を要求してくる。

## Decision

- `scripts/setup/deploy_all.py::_recover_wif_state` (主に WIF) と一般 deploy フローでは
  問題が起きた範囲だけを `-target=module.<name>` で絞って apply する運用を許容する
- 全 module 一括 apply はクリーン state 前提にし、partial recovery は意図的 `-target`
- partial 状態を long-lived に放置せず、一度 `make destroy-all` → `make deploy-all` で
  state を整える PDCA loop を default とする

## Consequences

- 学習用 dev project では `-target` 利用が日常的になる (production では推奨しない)
- `terraform plan` の結果が partial で読みにくくなることがあるので、`make tf-plan` の
  ログを必ず確認してから `apply` する運用を維持
