# ADR 0007 — KServe `storageUri` は `scripts/deploy/kserve_models.py` で `kubectl patch`、Terraform は manage しない

**Status**: Accepted
**Phase**: Phase 7 起点

## Context

Phase 7 の serving 層は KServe `InferenceService` で配備する。Vertex Model Registry の
`production` alias が指す model artifact を InferenceService の `storageUri` に流し込む
必要があるが、選択肢が 2 つある:

1. **Terraform で `storageUri` も管理**: `kubernetes_manifest` + `lifecycle.ignore_changes`
   で「初回作成のみ Terraform、以降は外部から書き換え許可」にする
2. **Manifest は placeholder で配置 + 別 script が patch**: TF / manifest は固定値、
   `scripts/deploy/kserve_models.py` が Vertex Model Registry を引いて `kubectl patch`

Phase 7 は ADR 0005 (Deployment env を manifest 側で管理) と同じ方針で、TF が触らない
原則を貫きたい。また Vertex Model Registry の alias resolution は GCP API call が必要で、
Terraform 側で `external` data source を組むより Python script の方が自然。

## Decision

- `infra/manifests/kserve/{encoder,reranker}.yaml` の `spec.predictor.model.storageUri` は
  literal placeholder (`gs://mlops-dev-a-models/encoders/multilingual-e5-base/v1/` 等)
- `scripts/deploy/kserve_models.py` が起動時:
  1. Vertex Model Registry から `property-{encoder,reranker}` の `production` alias を引く
  2. alias が指す version の `artifactUri` を取得
  3. `kubectl -n kserve-inference patch inferenceservice <name> --type=merge -p '{"spec":{"predictor":{"model":{"storageUri":"<uri>"}}}}'`
- `make deploy-kserve-models` がこの script の wrapper
- `scripts/ops/promote.py --bst-rename` が reranker 用に `model.txt` → `model.bst` を
  事前 copy する (KServe LGBServer v0.14 が `.bst` 拡張子のみ受け付ける制約への対処)

## Consequences

- TF apply / `make deploy-all` 後に **必ず `make deploy-kserve-models` を別途叩く運用**
  (`scripts/setup/deploy_all.py` の最終 step に組み込み済)
- Manifest 側の placeholder と production の `storageUri` が drift する (CI test では検知
  しない)。代わりに `scripts/ops/promote.py` の empty-artifact_uri guard が deploy 時に
  fail-fast する
- KServe を別の deploy mechanism (例: ArgoCD で alias を ConfigMap 化、Terraform で
  `kubernetes_manifest`) に切り替える判断をした場合、本 ADR を Superseded 化
