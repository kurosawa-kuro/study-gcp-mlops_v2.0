# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## このディレクトリの性質

MLOps 学習用の **7 フェーズ構成の親ディレクトリ** (Phase 7 = 到達ゴール)。  
全 phase を単一の親 Git リポジトリで管理する。フェーズを跨ぐ共通ビルド / テストは持たず、作業は常に各 phase 配下で完結する。

| Phase | ディレクトリ | テーマ | 学習の主題 |
|---|---|---|---|
| 1 | `1/study-ml-foundations/` | カリフォルニア住宅価格予測 | ML 基礎（学習・評価・保存） |
| 2 | `2/study-ml-app-pipeline/` | App + Pipeline + Port/Adapter | FastAPI / DI / core-ports-adapters 構成 |
| 3 | `3/study-hybrid-search-local/` | 不動産検索 (Local) | ハイブリッド検索 + Port/Adapter (Meilisearch + PostgreSQL + Redis + multilingual-e5) |
| 4 | `4/study-hybrid-search-gcp/` | 不動産検索 (GCP) | GCP マネージドサービス化 (Meilisearch on Cloud Run + BigQuery `VECTOR_SEARCH` + Terraform + WIF) |
| 5 | `5/study-hybrid-search-vertex/` | 不動産検索 (Vertex AI 本番MLOps基盤) | Vertex AI 本番MLOps プリミティブ化 (Pipelines / **Feature Store (Feature Group / Feature View / Feature Online Store) (training-serving skew 防止のため必須、PII / user_id は扱わない)** / **Vertex Vector Search (semantic 検索の本番 serving index、embedding 生成履歴・メタデータは BigQuery 側に保持)** / Model Registry / Monitoring v2)。Phase 4 の BigQuery `VECTOR_SEARCH` 経路を Vertex Vector Search に置換。**Phase 4 の Cloud Scheduler + Eventarc + Cloud Function trigger は軽量 orchestration 経路として継続** (Composer 本線化は Phase 6 で実施 = 引き算境界 Phase 5 → 6)。実装順序は **5A**(Pipelines/Registry/Endpoint) → **5B**(Feature Store) → **5C**(Vertex Vector Search) → **5D**(Monitoring/Dataform/Scheduled feature refresh) |
| 6 | `6/study-hybrid-search-pmle/` | GCP PMLE + 運用統合ラボ (引き算で派生) | **引き算チェーン (Phase 7 = canonical → 6 → 5 → ...) 上で Composer 本線昇格 + PMLE 追加技術 (BQML / Dataflow / Explainable AI / Monitoring SLO 等) が初登場する論理境界**。Phase 5 → 6 が Composer 本線化の引き算境界 (Vertex `PipelineJobSchedule` 完全撤去、Cloud Scheduler / Eventarc / Cloud Function trigger は軽量代替・smoke / manual trigger 用途で残置)。Feature Store / Vertex Vector Search は Phase 5 から継承。**実装本体は Phase 7 配下に集約** (Composer module / 3 DAG / PMLE 4 技術)、Phase 6 は引き算反映の派生 placeholder。実装順序は **6A**(Composer DAG 本線昇格) → **6B**(PMLE 追加技術統合)。不変は「不動産ハイブリッド検索というテーマとその中核コード」のみ |
| 7 | `7/study-hybrid-search-gke/` | 不動産検索 (GKE + KServe, 到達ゴール = canonical) | **教材コード完成版の到達ゴール / canonical 起点**。引き算で Phase 6 / 5 / 4 / 3 / 2 / 1 を後方派生する戦略 (親 README §4) のため、本 phase に **PMLE 4 技術 + Cloud Composer 本線 orchestration (`infra/terraform/modules/composer/` + 3 DAG) + Vertex AI Feature Store + Vertex Vector Search + Vertex AI Pipelines / Model Registry / BigQuery / Meilisearch を本実装**。Serving 層は Cloud Run → GKE Deployment + KServe InferenceService。Feature Online Store は KServe から **Feature View 経由で** opt-in 参照 (Phase 7 固有) |

Phase 1 -> 2 は「学習基礎」と「アプリ・設計パターン」を分離し、Phase 3 以降で検索ドメインに展開する。**Phase 7 = 到達ゴール / canonical 起点** であり、教材コード完成版は Phase 7 配下にすべて集約 (Composer / PMLE 4 技術 / Feature Store / Vector Search / GKE+KServe)。Phase 6 / 5 / 4 / 3 / 2 / 1 は **Phase 7 から引き算で派生する論理境界** (実装データ自体は Phase 7 のみ)。詳細は `README.md` §4 「基本戦略：「引き算」によるPhase間コード生成」を参照。

Phase 間でコードは共有しないが、**設計思想（Port/Adapter、`core -> ports <- adapters` の依存方向）は一貫**させ、adapter 実装だけ差し替えていく — これが phase を跨ぐ変更を判断するときの軸。複数 phase に同名の概念があっても、**実装 (adapter) の差し替えだけで済むか、思想 (port / core) 自体に触れるのかを必ず区別する**。

## 非負制約（Phase 3/4/5/6/7 共通）

- ハイブリッド検索の中核 **5 要素** を必須とする: **Meilisearch BM25 + multilingual-e5 + ベクトルストア (Phase 4 = BigQuery `VECTOR_SEARCH` / Phase 5+ = Vertex AI Vector Search) + RRF + LightGBM LambdaRank**
- この 5 要素を削除・置換・無効化する変更は、明示的な user 合意がない限り実施しない
- **Vertex Vector Search の役割 (Phase 5+)**: ME5 ベクトル検索の本番 serving index。embedding 生成履歴・メタデータの正本は BigQuery 側に置き続ける (data lake / serving index の二層構造)
- **Feature Store (Phase 5 必須)**: Vertex AI Feature Store (Feature Group / Feature View / Feature Online Store) により training-serving skew を防ぐ (Online Store を使う実務では **Feature View が serving 接続点**)。Phase 4 で BQ feature table / view の土台を作り、Phase 5 で格上げ。Phase 6 では Dataflow / Scheduled Query で更新パイプラインを強化、Phase 7 では KServe から Feature Online Store を Feature View 経由で opt-in 参照
- **Cloud Composer (Phase 7 で本実装、引き算で Phase 6 派生)**: Managed Airflow Gen 3 を本線オーケストレーターとして **Phase 7 で本実装** (`7/study-hybrid-search-gke/infra/terraform/modules/composer/` + `7/study-hybrid-search-gke/pipeline/dags/` の 3 DAG)。Phase 5 では Phase 4 から継続の Cloud Scheduler / Eventarc / Cloud Function 軽量経路を使う。本線 retrain schedule は Composer DAG (`daily_feature_refresh` / `retrain_orchestration` / `monitoring_validation` の 3 本) + PMLE 追加 step (Dataflow / BQML / drift)。**Vertex `PipelineJobSchedule` は完全撤去** (同一 PipelineJob 二重起動禁止)、**Cloud Scheduler / Eventarc / Cloud Function trigger は軽量代替・比較対象 / smoke / manual trigger 用途として残す** (本線 retrain と同じ job を別系統で起動しないこと = 二重起動禁止)。引き算チェーン (Phase 7 = canonical → 6 → 5 → 4) では Phase 5 → 6 が Composer 本線化の論理境界 (詳細は親 [`README.md` §「Cloud Composer の位置づけ」](README.md))
- **実案件 reference architecture**: Elasticsearch + Redis 同義語辞書 + ME5 + Vertex Vector Search + LightGBM (詳細は [`5/study-hybrid-search-vertex/docs/01_仕様と設計.md` §「実案件想定の reference architecture」](5/study-hybrid-search-vertex/docs/01_仕様と設計.md))。本リポは Meilisearch + Redis cache を **学習用 substitute** として据え置く。Port/Adapter で `MeilisearchAdapter` ↔ `ElasticsearchAdapter` の差し替えで到達可能な構造を維持。**Meilisearch を Elasticsearch に置換するのは user 合意必須**
- Phase 6 では **中核コード (`/search` デフォルト挙動) は絶対に変えない**。それ以外は PMLE 学習のため積極的に改変してよい (新 Port / Adapter / 新エンドポイント / 新 pipeline / 新 Terraform モジュール / feature flag 追加)

## 最重要ルール — 必ず phase 配下の CLAUDE.md を読む

作業対象フェーズが分かった時点で、**その phase 配下の `CLAUDE.md` を最優先で読む**。各 phase の CLAUDE.md には:

- 非負制約 (GCP プロジェクト / リージョン / Python / パッケージ管理等、User 確認無しに変えてはいけない項目)
- feature parity invariant (同一 PR で揃えるべき複数ファイル)
- `make` ターゲット一覧 + 実行順序
- ドキュメント衝突時の権威順位
- その phase 特有の「紛らわしい点」

が載っており、本ファイルの抽象的な説明より優先する。特に Phase 4 / 5 / 6 の CLAUDE.md は設計テーゼ / 非負制約 / parity invariant を載せた load-bearing なドキュメント。Phase 6 の CLAUDE.md には「中核コード以外は PMLE 学習のため自由に改変してよい」「labs/ 隔離 NG」の原則も明記されている。

親は単一 Git リポだが、各 phase は独立 Python 環境・独立 Makefile なので、**他 phase のコマンドや設計慣行をそのまま持ち込まない** (例: Phase 1 は Docker Compose + `make all`、Phase 4/5/6 は `uv` + `make sync && make check`)。

## 実行方式の段差（学習設計）

- Phase 1/2: Docker Compose 中心（ローカルで工程を理解）
- Phase 3: `uv` + Docker Compose 併用
- Phase 4/5: クラウド実行基盤中心（Cloud Run / BigQuery / Vertex AI）。Phase 4 で BQ feature table / view の土台 + 軽量 serverless orchestration (Cloud Scheduler / Eventarc / Cloud Function) を作り、Phase 5 で Feature Store + Vertex Vector Search に格上げ (orchestration は Phase 4 から継続の軽量経路を使う、Composer 本線化は Phase 6 で実施)
- Phase 6: 引き算チェーン上の **論理境界** (Phase 5 → 6 が Composer 本線化、PMLE 追加技術 (BQML / Dataflow / Explainable AI / Monitoring SLO 等) が初登場)。実装本体は Phase 7 配下に集約 (引き算で Phase 6 へ派生)。Feature Store / Vertex Vector Search は Phase 5 から継承
- Phase 7 (到達ゴール = canonical 起点): GKE + KServe serving + **Cloud Composer 本線 orchestration を本実装** (`infra/terraform/modules/composer/` + `pipeline/dags/` の 3 DAG)。Vertex AI Pipelines + Vertex Vector Search + Feature Store + PMLE 4 技術もすべて本 phase 配下。KServe から Feature Online Store を Feature View 経由で opt-in 参照する経路を追加。**orchestration 二重化を作らない** (Composer DAG が本線、軽量経路は smoke/manual)

この段差は、設計思想を維持したまま実行基盤を段階的に差し替える教材設計のためのもの。**コード自体は Phase 7 = canonical 起点に集約**し、引き算で後方 Phase の docs / 仕様書を派生させる。Phase 6 は「基盤を差し替える」phase ではなく「同じ基盤に追加技術を adapter / 副経路として統合する論理段階」(実コードは Phase 7 のみ)。

## フェーズ横断の原則

- **phase 選択**: ユーザ指定がなければ、変更対象ファイルの phase のルールに従う。ファイルが特定できない場合は確認する
- **phase 跨ぎの変更**: 全 phase を触るリファクタや機械的移行以外では、複数 phase を同時に変更しない。同じ概念名でも実装が違うことが多い
- **`OLD-study-gcp-mlops-hybrid-search-vertex/` / `study-gcp-mlops-pmle/`** — アーカイブ。参考資料として読むのは可、修正は User の明示指示がない限り触らない
- **トップレベルの日本語 md** (`ランキング最適化ロジック.md` / `簡易代替技術.md` / `類似テーマ.md`) は設計メモ・アイデアストック。コード側との整合は保証されない

## コマンド早見

phase ごとに設計思想が違うので、`make help` を最初に叩く:

```bash
cd 1/study-ml-foundations && make               # 実装データ削除済 (`pre-phase1-impl-removal` tag で復元可)。docs/ のみ残置
cd 2/study-ml-app-pipeline && make              # Docker Compose 系: build/seed/train/serve/test
cd 3/study-hybrid-search-local && make help     # 実装データ削除済 (`pre-phase3to6-impl-removal` tag で復元可)。docs/ のみ残置
cd 4/study-hybrid-search-gcp && make help     # 実装データ削除済 (同上)。docs/ のみ残置
cd 5/study-hybrid-search-vertex && make help    # 実装データ削除済 (`pre-phase3to6-impl-removal` tag で復元可)。docs/ のみ残置
cd 6/study-hybrid-search-pmle && make help      # 実装データ削除済 (同上)。docs/ のみ残置
cd 7/study-hybrid-search-gke && make help       # canonical 起点。Composer 本実装 + PMLE 4 技術 + Feature Store + Vector Search + GKE + KServe (到達ゴール)
```

Phase 4 / 5 / 6 / 7 はローカル CI 同等チェックとして `make check` (ruff + ruff format --check + mypy strict + pytest) があり、変更後はこれを走らせる。Phase 1 / 2 は `make test` (pytest のみ)、Phase 3 は `make test` + `make check-layers` + `make verify-pipeline`。

## 参照リポジトリ (Phase 4 / 5 が継承元として挙げるもの)

- `/home/ubuntu/repos/study-gcp-mlops/study-llm-reranking-mlops` — 不動産ハイブリッド検索設計 (LambdaRank / NDCG / ME5)
- `/home/ubuntu/repos/starter-kit/mlops/` — GCP I/O 層 (GCS / BQ insert / Cloud Logging)
- `/home/ubuntu/repos/study-gcp/study-gcp-mlops/` — Terraform + CI/CD 雛形

これらは本リポ外なので、パスが実在するかは必要時に確認する。

## current sprint の正本 (`docs/TASKS.md`)

各 phase の `docs/TASKS.md` を **current sprint の正本** とする。「現在の目的 / 今回の作業対象 / 今回はやらない / 完了条件 / 実装済 / 未実装」を 1 ファイルに集約。長期 backlog/index は従来通り `docs/tasks/02_移行ロードマップ.md`、過去判断履歴は `docs/decisions/` (Phase 1/2/6/7)。権威順位は `02 > TASKS > 01 > README > CLAUDE`。

**Phase 7 のみフォルダ構造**: Phase 7 では docs/ 配下を `architecture/` (01,03) / `tasks/` (TASKS, TASKS_ROADMAP) / `runbook/` (04,05) / `decisions/` / `conventions/` に再編済。`docs/tasks/TASKS.md` (current sprint) / `docs/tasks/TASKS_ROADMAP.md` (長期 backlog + Wave 1-3 詳細) / `docs/architecture/01_仕様と設計.md` / `docs/runbook/04_検証.md` / `docs/runbook/05_運用.md` を正本とする。Phase 1-6 は従来構造 (番号付き flat、`docs/02_移行ロードマップ.md` 等) を維持。

## Claude Code 標準セット (`.claude/` 一式)

phase 横断のエージェント / スキル / コマンド / フックは **root `.claude/`** に集約する (各 phase の `.claude/` は基本的に空、phase 固有ルールは `<phase>/CLAUDE.md` のみ)。最小構成から開始し、有用性が出たもののみ追加する方針 (User memory「学習リポなので最小スペック」「dockerignore は最小から」と整合)。詳細仕様は [`/home/ubuntu/.claude/plans/enchanted-discovering-thacker.md`](/home/ubuntu/.claude/plans/enchanted-discovering-thacker.md)。

| 種別 | 名前 | 用途 |
|---|---|---|
| agent | `port-adapter-boundary-reviewer` | diff の Port-Adapter 境界違反 (adapter import 漏れ / RULES 更新忘れ / noop_adapter 不足 / DI 配線忘れ) を検出。`make check-layers` の補完。read-only |
| agent | `feature-parity-checker` | 特徴量変更 PR の **6 ファイル parity** を検証 (Dataform / `build_ranker_features` / `FEATURE_COLS_RANKER` / TF `ranking_log.features` / `validate_feature_skew.sql` / Vertex Feature Group)。read-only |
| agent | `phase-subtraction-derivator` | Phase 7 → Phase 6/5/4/... の引き算 diff プレビュー (削除対象 / adapter 差し替え / 不変 Port を提示)。read-only、proposal のみ |
| skill | `phase-doc-sync` | phase 横断 doc 同期。`.github/skills/phase-doc-sync/SKILL.md` の複製 (両方 canonical) |
| skill | `port-adapter-scaffolder` | 新 Port を切るときの 6 ステップ (Port → Noop adapter → RULES → Fake → composition root → 本番 adapter → 03_実装カタログ追記) |
| command | `/check-parity` | `feature-parity-checker` を呼ぶ薄い wrapper |
| hook | `SessionStart` (`hooks/show-tasks.sh`) | phase root を解決し `docs/tasks/TASKS.md` (Phase 7) または `docs/TASKS.md` (Phase 1-6) の先頭 50 行を表示。phase 外では何もしない |
| hook | `PostToolUse` (`hooks/check-layers.sh`) | Edit/Write/MultiEdit の対象が Port-Adapter sensitive area (app/services/, app/composition_root.py, app/api/, app/domain/, app/schemas/, ml/<feat>/{ports,adapters}/, pipeline/<job>/ports/, pipeline/dags/, scripts/ci/layers.py) なら `make check-layers` をバックグラウンド実行、失敗時のみ stderr に短い出力 |

その他:

- `.github/agents/gcp-mlops-theme-research.agent.md` — 検索/ランキング設計比較と markdown 提案専用 agent (GitHub 側 user-invocable, コード変更なし)。`.claude/` 集約後も `.github/` 側に残置 (Github Actions 側からの参照可能性のため)
- `.claude/settings.local.json` (gitignore 対象) — 個人ごとの permissions allowlist。team 共有の hooks は `.claude/settings.json` に書く

**Claude Code に任せる作業 vs 人間判断** (要約、詳細は plan ファイル §5.5):

- **任せる**: Port/adapter/fake の boilerplate 提案、6 ファイル parity 同期、doc 同期、テスト雛形、`scripts/ci/layers.py` の `RULES` 追記提案、引き算 diff プレビュー、`mlops-dev-a` への `terraform apply` / `make deploy-all` (Phase 7 CLAUDE.md 事前承認範囲)
- **人間判断**: 中核コード変更 (`search_service.py` / `ranking.py` / `build_ranker_features`)、hybrid-search 5 要素の変更、Composer 二重起動判定、高/低スペック選択、Meilisearch → Elasticsearch 等の置換、ADR 起案、`git push --force` / 共有 main への push、別 project への波及
