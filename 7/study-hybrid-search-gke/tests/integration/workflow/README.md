# tests/integration/workflow/

Phase 7 の **workflow contract** を pin する pytest 群。

`unit/` が pure logic、`parity/` が lock-step 不変条件を守るのに対して、
ここは **「PDCA 本線がまだ 1 発で成立するか」** を構造的に守る。

対象例:

- `deploy-all` の step 順序
- `seed-test -> sync-meili -> backfill-vvs -> trigger-fv-sync` の依存順
- runtime ConfigMap overlay への Terraform outputs 注入
- 「手動 patch / 手動 sync が必要」に退化していないこと

原則:

1. local/offline でも回ること
2. 実 GCP を叩かずに workflow wiring の崩壊を検知できること
3. 「この順序や配線が壊れると deploy-all 1 発が崩れる」と 1 行で説明できること

実 GCP を前提にする acceptance gate は `tests/e2e/` に置く。
