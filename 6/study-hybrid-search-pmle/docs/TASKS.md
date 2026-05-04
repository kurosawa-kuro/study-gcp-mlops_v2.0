# TASKS.md (Phase 6)

`docs/02_移行ロードマップ.md` (長期 backlog/index) の current-sprint 抜粋。

## 現在の目的

Phase 6 = Phase 5 完成系に **PMLE 追加技術 (BQML / Dataflow / Explainable AI / Monitoring SLO)** を adapter / 追加エンドポイント / 追加 Terraform として実統合し、**Cloud Composer (Managed Airflow Gen 3) を本線 orchestration に昇格**するフェーズ。Phase 5 → 6 の引き算境界 = Phase 5 までの Cloud Scheduler + Eventarc + Cloud Function trigger + Vertex `PipelineJobSchedule` の orchestration 責務を Composer DAG に集約。

不変は「不動産ハイブリッド検索というテーマと中核コード (`/search` デフォルト挙動)」のみ。それ以外は PMLE 学習のため積極的に改変してよい (CLAUDE.md `feedback_phase6_direction.md` 既知ルール: labs/ 隔離 / 問題集形式は NG)。

## 今回の作業対象

実装順序は **6A**(Composer DAG 本線昇格) → **6B**(PMLE 追加技術統合)。

- 6A: Cloud Composer DAG 本線昇格 (`daily_feature_refresh` / `retrain_orchestration` / `monitoring_validation` の 3 本)
- 6B: PMLE 4 技術 (BQML popularity / Dataflow streaming / Explainable AI TreeSHAP / Monitoring SLO + burn-rate)

## 今回はやらない

- 中核コード (`/search` デフォルト挙動 / Meilisearch + Vertex Vector Search + ME5 + RRF + LightGBM LambdaRank) の置換 — User 合意必須
- GKE / KServe / Gateway API (Phase 7 へ)
- Vertex `PipelineJobSchedule` の継続使用 — 6A で完全撤去 (二重起動禁止)
- 全 Phase 共通禁止技術

## 完了条件

- [x] `make check` (CI 同等) 通過
- [x] Composer DAG 3 本のデプロイ + retrain schedule の Composer 集約
- [x] PMLE 4 技術の adapter / endpoint / Terraform 統合
- [x] Feature parity invariant (6 ファイル同 PR 原則) を維持

## 実装済 (Phase 6 観点)

### 6A: Composer DAG 本線昇格
- [x] Cloud Composer 環境 (Managed Airflow Gen 3, asia-northeast1)
- [x] `daily_feature_refresh` DAG (Feature Store 更新)
- [x] `retrain_orchestration` DAG (Vertex AI Pipelines 起動)
- [x] `monitoring_validation` DAG (BQ monitoring query)
- [x] Vertex `PipelineJobSchedule` 撤去
- [x] Cloud Scheduler / Eventarc / Cloud Function は smoke / manual trigger 用に残置

### 6B: PMLE 追加技術統合
- [x] BQML property-popularity model (`make bqml-train-popularity`)
- [x] Dataflow Flex Template (streaming 強化)
- [x] Explainable AI TreeSHAP (reranker explain pod)
- [x] Monitoring SLO + burn-rate (`make ops-slo-status`)

## 未実装 / 残タスク

Phase 7 への引き継ぎ準備として進行中の項目があれば `02_移行ロードマップ.md` を参照。本 Phase 単独での未着手残件は基本無し。

## 次 Phase

`7/study-hybrid-search-gke/` — Phase 6 完成系の **serving 層のみ** を GKE Deployment + KServe InferenceService に差し替える到達ゴール。Composer / Feature Store / Vertex Vector Search / Model Registry はそのまま継承。
