# monitoring/ — Phase 5

## 構成物

- `validate_data_skew.sql` — 学習(過去90日)と推論(直近1日)の特徴量分布を比較。Scheduled Query で `mlops.validation_results` に 1 日 1 回 insert。Terraform `google_bigquery_data_transfer_config.skew_check` から読み込み
- ログベースメトリクス (`infra/modules/monitoring/main.tf`):
  - `search_api_5xx` — Cloud Run 5xx カウント
  - `search_api_latency_ms` — `request completed` 構造化ログから `latency_ms` をDistribution メトリクス化
- アラートポリシー:
  - `search-api 5xx > 1% over 10m`
  - `search-api p95 latency > 500ms over 10m`
- 通知: `email` チャネル (placeholder, Terraform で差し替え)

## 精度追跡

遅延ラベル到着時に UPDATE で `predictions_log.label` を埋め、別 Scheduled Query で
過去 7 日と過去 14 日の MAE 差分を計算 → `validation_results` に `metric='accuracy_degradation'` で書き込み。Phase 6 の再学習判定で使用。
