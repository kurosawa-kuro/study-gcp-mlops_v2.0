# E2E Tests

`tests/e2e/` は **opt-in live acceptance** を置く場所。

- 常時 CI で回す structural / workflow contract は `tests/integration/` に置く
- ここは GCP / GKE / KServe を前提にする **高コスト** な acceptance のみ

## テストの役割分担（重要）

| ファイル | 環境変数 | 内容 |
|---|---|---|
| `test_phase7_acceptance_gate.py` | `RUN_LIVE_GCP_ACCEPTANCE=1` | **deploy 済み**クラスタに対する canonical 検証（ConfigMap / ops-search-components / VVS / Feature Group / feedback / ranking / accuracy）。**V6 の正本**。 |
| `test_phase7_full_recreate_gate.py` | `RUN_LIVE_GCP_FULL_RECREATE=1` | `destroy-all` → `deploy-all` → **上と同一チェック**。Vertex Feature Store 等の **非同期削除**により `deploy-all` が 409 になり得る — **検証設計として不安定**な別ゲート。 |

**混ぜない**: 死守ラインや通常の V6 で見たいのは前者。後者は「フル PDCA 再現が通るか」のオプション検証。

## コマンド例

```bash
# V6（既存環境）
RUN_LIVE_GCP_ACCEPTANCE=1 pytest tests/e2e/test_phase7_acceptance_gate.py -m live_gcp

# Full recreate（破壊的・フレークし得る）
RUN_LIVE_GCP_FULL_RECREATE=1 pytest tests/e2e/test_phase7_full_recreate_gate.py -m 'live_gcp and full_recreate'
```

`deploy-all` は `scripts/infra/vertex_feature_store_wait.py` で Feature Group / Feature Online Store 名の解放を待ってから tf-apply する（destroy 直後の 409 緩和）。
