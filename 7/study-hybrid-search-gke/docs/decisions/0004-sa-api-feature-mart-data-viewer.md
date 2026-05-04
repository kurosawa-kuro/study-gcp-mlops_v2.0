# ADR 0004 — `sa-api` の `feature_mart` データセットへの dataViewer 配線

**Status**: Accepted
**Phase**: Phase 4 起点 → Phase 5 / 6 / 7 継承

## Context

Phase 4 初期構成では `sa-api` (search-api ランタイム SA) には `mlops` データセットへの
`bigquery.dataViewer` のみ付与していた。Phase 5 で `feature_mart` データセット
(Dataform 出力 + property_embeddings 等) を導入したとき配線を漏らし、`/search` ハンドラが
`property_embeddings` への `VECTOR_SEARCH` で 403 を返す事故が発生。

ログには `403 Permission denied: User does not have bigquery.tables.getData` が出るが、
search-api の adapter 側では generic exception として扱われるため、根本原因の特定に
時間が掛かった。

## Decision

- `infra/terraform/modules/data/main.tf` に `api_feature_viewer` resource (`sa-api` →
  `feature_mart` への `roles/bigquery.dataViewer`) を明示配線
- `tests/integration/infra/test_terraform_module_structure.py` で iam binding が
  data module に存在することを構造的に pin (毎モジュール `main.tf` / `variables.tf` /
  `outputs.tf` / `versions.tf` の 4 ファイル構成 + variable description)
- 新 dataset を追加するときは **必ず sa-api の reader binding も同 PR で追加** する慣例

## Consequences

- 配線が `iam` module ではなく `data` module 側にある (binding の subject = SA、
  resource = dataset の場合は dataset 側に置く Terraform 慣例に従った)
- 別 SA が `feature_mart` を読みたくなったときは同パターンで data module に追加する
