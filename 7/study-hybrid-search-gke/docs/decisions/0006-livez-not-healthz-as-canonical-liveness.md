# ADR 0006 — Cloud Run `/healthz` 予約名回避のため app は `/livez` を canonical liveness にする

**Status**: Accepted
**Phase**: Phase 4 起点 (Cloud Run 期) → Phase 7 (GKE) でも踏襲

## Context

Phase 4-6 の Cloud Run 環境では、GFE (Google Front End) が `/healthz` を **HTML 404 で
横取り** する仕様があり、app 側で `/healthz` を 200 で実装してもクライアントには到達しない
ことが発生 (Phase 5 inheritance bug)。

Phase 7 は GKE に移行したので Cloud Run の制約自体は外れたが、ops script (`scripts/ops/livez.py`)
や Makefile (`make ops-livez`) を含む既存ツール群が `/livez` を canonical として叩いている。
ここで GKE 環境で `/healthz` を canonical に戻すと cross-phase の operability が壊れる。

## Decision

- App は `/livez` を canonical 200 endpoint とする (`app/api/routers/health_router.py`)
- `/healthz` は `/livez` の alias として併設 (test 互換 + ローカル `make api-dev`)
- `/readyz` は別途 `Container.candidate_retriever` + `encoder_client` の wired 状態を
  検査する真の readiness (`infra/manifests/search-api/deployment.yaml::readinessProbe`)
- ops 系 script / make target / smoke check は `/livez` を叩く
- `tests/integration/infra/test_manifests_structure.py::test_search_api_deployment_probes_have_canonical_paths`
  で `startupProbe` + `livenessProbe` = `/livez` / `readinessProbe` = `/readyz` を pin

## Consequences

- 環境別に endpoint 名を分岐せず cross-phase で同じ ops vocabulary を維持できる
- Cloud Run に戻すケース (Phase 4-6 リポを再利用) でも変更不要
- `/healthz` alias を残すコストはわずかだが、削除するときは ops 側の互換も同時に切る
