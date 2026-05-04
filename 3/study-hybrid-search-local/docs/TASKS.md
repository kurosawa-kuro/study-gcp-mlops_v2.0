# TASKS — Phase 3 (current sprint)

> 現在の目的: Phase 7 (canonical) からの引き算で **Local 完結ハイブリッド検索アプリ** を再構築。
> 計画の正本は [`02_移行ロードマップ.md`](02_移行ロードマップ.md)。

## 現在の目的

Phase 3 を **Phase 4 (GCP MLOps 土台) への足し算起点** として完成させる。
- 不変 Port (Phase 7 と完全同型) を維持
- 中核 5 要素 (Meilisearch BM25 + ME5 + pgvector + RRF + LightGBM LambdaRank) を Local 完結で動かす
- `make build && make seed && make train && make serve` で `/search` が 3 系統 all non-zero を返す

## Wave 1: スキャフォールディング — 完了 ✅

- [x] `pyproject.toml` (uv workspace、Phase 7 から GCP 依存削除)
- [x] `Makefile` (`build` / `seed` / `train` / `evaluate` / `serve` / `test` / `check` / `check-layers` / `verify-pipeline`)
- [x] `docker-compose.yml` (postgres + pgvector / meilisearch / redis / search-api 4 service)
- [x] `definitions/postgres/migrations/0001_init.sql` (5 テーブル DDL + `CREATE EXTENSION vector`)
- [x] `env/config/setting.yaml` / `env/secret/credential.yaml.example`
- [x] `infra/run/services/api/Dockerfile` / `infra/run/jobs/pipeline/Dockerfile`
- [x] `.gitignore` / `.dockerignore` / ディレクトリ骨格

## Wave 2: Port + Local Adapter + FastAPI app — 完了 ✅

- [x] Phase 7 から Domain / Schema / 8 Port / Service / 3 Noop adapter / Router / dependencies / mappers / middleware を copy
- [x] `app/services/search_service.py` を改修 (popularity_scorer 削除)
- [x] 8 Phase 3 Local adapter を新規:
  - [x] `MeilisearchLexicalSearch` (Phase 7 の MeilisearchLexical を認証簡略化)
  - [x] `LocalE5Encoder` (sentence-transformers in-process)
  - [x] `PgVectorSemanticSearch` (PostgreSQL + pgvector)
  - [x] `LocalLightGBMReranker` (Booster.predict in-process)
  - [x] `PostgresFeatureFetcher`
  - [x] `PostgresRankingLogPublisher`
  - [x] `PostgresFeedbackRecorder`
  - [x] `LocalCandidateRetriever` (lexical + semantic + RRF + Postgres enrich)
- [x] `app/settings.py` / `app/composition_root.py` / `app/main.py` 新規
- [x] `scripts/ci/layers.py` を Phase 3 用に簡素化

## Wave 3: ML パイプライン — 完了 ✅

- [x] `pipeline/data_job/main.py` (合成 1000 件 + Meilisearch index + pgvector embedding + feature_mart)
- [x] `ml/training/trainer.py` を Phase 3 用 minimal に書き直し (GCS / Vertex Experiments 撤去)
- [x] `ml/registry/artifact_store.py` (`LocalArtifactStore`)
- [x] `pipeline/training_job/main.py` (CLI ラッパ)
- [x] `pipeline/evaluation_job/main.py` (NDCG@10 / MAP / Recall@20)
- [x] `Makefile` の `seed` / `train` / `evaluate` target 配線

## Wave 4: 検証 + docs 整備 — 進行中 🟡

- [x] `docs/03_実装カタログ.md` 再生成
- [x] `docs/04_運用.md` 再生成
- [x] 本ファイル (`docs/TASKS.md`) 再生成
- [x] `tests/conftest.py` 新規
- [x] `tests/_fakes/__init__.py` を Phase 3 用 (3 stub 除外)
- [x] `tests/unit/app/test_search_service_smoke.py` 新規
- [ ] **🔧 ローカル E2E 検証 (user 環境で実施)**:
  - [ ] `make build` で 3 service `healthy`
  - [ ] `make up && make seed && make train` PASS
  - [ ] `make serve` 起動後 `curl /search` で 3 系統 all non-zero、rerank score が学習済モデル由来
  - [ ] `make check-layers` 違反ゼロ
  - [ ] `make check` (ruff + mypy + pytest) PASS
  - [ ] `make verify-pipeline` PASS
  - [ ] NDCG@10 > random ベースライン

## 次の Phase (Phase 4 への足し算)

Phase 3 完了後、Phase 4 で以下を **追加** (置換でなく並行追加):

- `CloudRunIdentityMeilisearchLexical` / `CloudRunHttpEncoderClient` / `BigQueryVectorSearchSemanticSearch` / `BigQueryFeatureFetcher` / `PubSubRankingLogPublisher` / `PubSubFeedbackRecorder`
- `composition_root.py` の選択ロジックで feature flag (`SEMANTIC_BACKEND` 等) で切替
- Terraform / WIF / Secret Manager / Artifact Registry / Cloud Build / GitHub Actions 追加
- 軽量 retrain trigger (Cloud Scheduler + Eventarc + Cloud Function (Gen2)) 追加

不変 Port は変えない。

## 関連ドキュメント

- [`02_移行ロードマップ.md`](02_移行ロードマップ.md) — 権威 1 位、決定的仕様
- [`01_仕様と設計.md`](01_仕様と設計.md) — Phase 3 固有の差分
- [`03_実装カタログ.md`](03_実装カタログ.md) — 実装スナップショット
- [`04_運用.md`](04_運用.md) — make ターゲット早見 / トラブルシューティング
- [Phase 7 docs/architecture/01_仕様と設計.md](../../../7/study-hybrid-search-gke/docs/architecture/01_仕様と設計.md) — canonical 完成版
