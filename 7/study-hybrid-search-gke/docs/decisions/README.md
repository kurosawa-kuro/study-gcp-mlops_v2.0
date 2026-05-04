# Architecture Decision Records (ADR)

Phase 6 → Phase 7 で継承された **恒久対処ギャップ** を 1 件 1 ファイルで記録する場所。
インラインコメントや `docs/03_実装カタログ.md` 冒頭の bullet list だと
Phase 8 以降で見落とされやすいため、独立した ADR として切り出している。

## 形式

各 ADR は次の節を持つ:

- **Context**: なぜこの決定が必要になったか (再現したインシデント、確認した制約)
- **Decision**: 採用した対処の概要
- **Consequences**: 副作用 / 運用上の追加負担
- **Status**: `Accepted` (現役) / `Superseded` (置き換え) / `Deprecated` (撤去予定)
- **Phase**: 起点 phase + 継承された phase

## 一覧 (Phase 7 時点)

| ID | タイトル | Status |
|---|---|---|
| 0001 | BQ table の `deletion_protection=true` を `terraform destroy` 前に state-flip する | Accepted |
| 0002 | 半 destroy 後の SA / Dataset IAM orphan を `-target` で部分 apply する | Accepted |
| 0003 | WIF pool/provider の 30 日 soft-delete に対する `_recover_wif_state` 自動 undelete | Accepted |
| 0004 | `sa-api` の `feature_mart` データセットへの dataViewer 配線 | Accepted |
| 0005 | Phase 7 で Deployment env は manifest 側で管理し Terraform は touch しない | Accepted |
| 0006 | Cloud Run `/healthz` 予約名回避のため app は `/livez` を canonical liveness にする | Accepted |
| 0007 | KServe `storageUri` は `scripts/deploy/kserve_models.py` で `kubectl patch`、Terraform は manage しない | Accepted |
| 0008 | `module.kserve` の K8s/Helm リソースは GKE cluster より先に target destroy する | Accepted |

## 追加 / 更新ルール

- 新規 ADR は **連番 4 桁 + `-` + kebab-case タイトル** で `docs/decisions/<NNNN>-<slug>.md` に作成
- 既存 ADR の状況が変わったら **本ファイル (上記表) と当該 ADR の Status を同時に更新**
- 撤去 (= 制約事項が解消した) する場合は ADR を削除せず Status を `Superseded` / `Deprecated` に変更し、後継 ADR があれば link
- ADR 番号の reuse は禁止 (履歴を追えなくなるため)
