# AGENTS.md

## Purpose

Agent operating guide for this monorepo-style learning project.
Use this file for cross-phase behavior only; phase-specific details belong to each phase-local doc.

This file is the **Cursor / Codex-style project charter** for agents (parallel to root [`CLAUDE.md`](CLAUDE.md), which is optimized for Claude Code). Prefer [`CLAUDE.md`](CLAUDE.md) for the fullest constraint text; use this file for quick routing and **tool-equivalence** below.

### Claude Code ↔ Cursor mapping (concept-level)

| Claude Code concept | Role | Cursor equivalent in this repo |
| --- | --- | --- |
| `CLAUDE.md` | Always-loaded charter, build/test, bans | [`CLAUDE.md`](CLAUDE.md) + this [`AGENTS.md`](AGENTS.md) + `<phase>/CLAUDE.md` |
| `.claude/rules/` | Path- or mode-specific rules | [`.cursor/rules/*.mdc`](.cursor/rules/) (this repo has no `.claude/rules/`; rules are split between `CLAUDE.md` and `.cursor/rules/`) |
| Subagents / custom agents | Specialized agent prompts | Cursor Agent / Cloud Agent; **reference prompts** (read-only handoff): [`.claude/agents/*.agent.md`](.claude/agents/) |
| Skills | Reusable procedures | Cursor **Agent Skills** (editor-level); repo sources: [`.claude/skills/`](.claude/skills/), [`.github/skills/`](.github/skills/) |
| Slash commands / commands | Manual bootstraps | [`.cursor/commands/`](.cursor/commands/) and [`.claude/commands/`](.claude/commands/) (keep text in sync when possible) |
| Hooks | Deterministic post-edit scripts | [`.claude/hooks/`](.claude/hooks/) (Claude Code). Cursor: optional [Hooks](https://cursor.com) or rely on CI / `make check` |
| MCP | External systems | Configured in Cursor **MCP** settings (per user/env) |
| Review rules | Reviewer policy, bug patterns | [`.cursor/rules/`](.cursor/rules/) + team review / Bugbot if enabled |

### Tool surface mapping (where each concern lives)

| Concern | Claude Code | Cursor (this repo) |
| --- | --- | --- |
| Charter / “read first” | `CLAUDE.md` | `AGENTS.md` + `CLAUDE.md` |
| Fine-grained rules | `CLAUDE.md` sections + (optional) `.claude/rules/` | `.cursor/rules/*.mdc` |
| Agent role prompts | `.claude/agents/*.agent.md` | Same files as **documentation**; paste or @-reference in chat when simulating that role |
| Skills | `.claude/skills/<name>/SKILL.md` | Same paths; optional mirror in user Agent Skills |
| Commands | `.claude/commands/*.md` | `.cursor/commands/*.md` |

## Repository Shape

- This repository contains independent phases under `1/` through `7/`.
- Do not share implementation code across phases unless explicitly requested.
- Keep changes scoped to one phase whenever possible.

Primary navigation:
- [README.md](README.md)
- [CLAUDE.md](CLAUDE.md)
- [docs/README.md](docs/README.md)

## First Step For Any Task

1. Identify the target phase from the file path.
2. Read that phase's `CLAUDE.md` before editing code.
3. Prefer phase-local docs as source of truth when docs conflict.

Phase-local guides:
- [1/study-ml-foundations/CLAUDE.md](1/study-ml-foundations/CLAUDE.md)
- [2/study-ml-app-pipeline/CLAUDE.md](2/study-ml-app-pipeline/CLAUDE.md)
- [3/study-hybrid-search-local/CLAUDE.md](3/study-hybrid-search-local/CLAUDE.md)
- [4/study-hybrid-search-gcp/CLAUDE.md](4/study-hybrid-search-gcp/CLAUDE.md)
- [5/study-hybrid-search-vertex/CLAUDE.md](5/study-hybrid-search-vertex/CLAUDE.md)
- [6/study-hybrid-search-pmle/CLAUDE.md](6/study-hybrid-search-pmle/CLAUDE.md)
- [7/study-hybrid-search-gke/CLAUDE.md](7/study-hybrid-search-gke/CLAUDE.md)

## Command Conventions

- Start in the target phase directory before running `make`.
- Use `make help` first in each phase.
- Command vocabulary and phase support matrix: [docs/conventions/Makefile規約.md](docs/conventions/Makefile規約.md).

Validation expectations:
- Phase 1-2: usually `make test`.
- Phase 3: `make test` plus layer/pipeline checks when relevant.
- Phase 4-7: `make check` (lint/format/type/test equivalent).

## Non-Negotiable Constraints

- For phases 3-7, keep the hybrid-search **5-element core** intact: **Meilisearch BM25 + multilingual-e5 + vector store (Phase 4 = BigQuery `VECTOR_SEARCH` / Phase 5+ = Vertex AI Vector Search) + RRF + LightGBM LambdaRank**.
- For phases 5-7, the **Vertex AI Feature Store (Feature Group / Feature View / Feature Online Store)** trio is mandatory (training-serving skew prevention). Phase 4 prepares the BigQuery feature table / view foundation; Phase 6 strengthens the update pipeline (Dataflow / Scheduled Query); Phase 7 adds opt-in Feature Online Store reference from KServe.
- For phases 6-7, **Cloud Composer (Managed Airflow Gen 3)** is the canonical orchestrator. Phase 6 promotes Composer to the main line and absorbs Phase 5's Cloud Scheduler / Eventarc / Cloud Function / Vertex `PipelineJobSchedule` triggers into 3 DAGs (`daily_feature_refresh` / `retrain_orchestration` / `monitoring_validation`). Vertex `PipelineJobSchedule` must be removed from Phase 6 onward (no double-trigger). Phase 7 inherits the same DAGs unchanged. Phase 5 must NOT introduce Composer — it continues to use Phase 4's lightweight serverless orchestration.
- Vertex Vector Search (Phase 5+) is the **production serving index** for ME5 vector search. The canonical embedding history / metadata stays in BigQuery (data lake + serving index two-layer model).
- Any replacement/removal of core retrieval/ranking/feature-store/vector-store components requires explicit user approval. Meilisearch is a learning-friendly substitute for the real-world reference architecture (Elasticsearch + Redis synonym dictionary); swap requires explicit user approval.
- Phase 6 keeps `/search` default behavior aligned with Phase 5; new PMLE features should be opt-in.
- Phase 7 is the **arrival goal** (not optional). It inherits everything from Phase 6 and replaces only the serving layer with GKE + KServe.

Canonical references:
- [README.md](README.md)
- [CLAUDE.md](CLAUDE.md)
- [docs/01_仕様と設計.md](docs/architecture/01_仕様と設計.md)
- [docs/03_実装カタログ.md](docs/architecture/03_実装カタログ.md)
- [docs/04_運用.md](docs/runbook/04_運用.md)
- [docs/conventions/Docker配置規約.md](docs/conventions/Docker配置規約.md)
- [docs/conventions/README.md](docs/conventions/README.md) — 規約・配置・命名 5 ファイルの索引

## Cross-Phase Architecture Snapshot

Single line per phase, showing how the hybrid-search stack is upgraded step by step. Use this when you need to make a cross-phase judgment without opening individual phase docs.

| Phase | Lexical | Vector store | Feature store | Serving runtime |
|---|---|---|---|---|
| 3 (Local) | Meilisearch (Docker) | pgvector / 簡易 ANN | local files | uv + Docker Compose |
| 4 (GCP) | Meilisearch on Cloud Run | **BigQuery `VECTOR_SEARCH`** | **BigQuery feature table / view** (Phase 5 Feature Store の入力源) | Cloud Run |
| 5 (Vertex AI 本番MLOps基盤) | Meilisearch on Cloud Run | **Vertex AI Vector Search** (BigQuery 側に embedding 履歴・メタデータ正本) | **Vertex AI Feature Store (Feature Group / Feature View / Feature Online Store)** (必須) | Vertex AI Endpoint (orchestration は Phase 4 軽量経路を継続) |
| 6 (PMLE + 運用統合) | inherits Phase 5 | inherits Phase 5 | inherits Phase 5 + Dataflow / Scheduled Query で更新パイプライン強化 + Composer DAG で更新管理 | Vertex AI Endpoint + **Cloud Composer 本線 orchestration** (Phase 5 までの軽量経路を集約) |
| 7 (GKE/KServe, 到達ゴール) | inherits Phase 6 | inherits Phase 6 | inherits Phase 6 + KServe から Feature Online Store opt-in 参照 | GKE Deployment + KServe InferenceService (Composer は Phase 6 から継承) |

Real-world reference architecture (in design docs only, not in code): Elasticsearch + Redis 同義語辞書 + ME5 + Vertex AI Vector Search + LightGBM. The repo intentionally substitutes Meilisearch + Redis cache for learning-friendliness.

## Documentation Rules

- Link to existing docs instead of duplicating long policy text.
- Treat root docs as navigation/hubs; treat phase-local docs as operational source of truth.
- Archive/history lives under [docs/archive/README.md](docs/archive/README.md).

## Guardrails

- Do not edit archive or legacy material unless asked.
- Do not perform broad multi-phase refactors by default.
- For root-level doc updates, keep terminology synchronized with phase docs.

## Existing Chat Customizations

- Cursor rules: [`.cursor/rules/`](.cursor/rules/) (`study-gcp-mlops-core.mdc`, `python-fastapi-ml.mdc`, `terraform-gcp-mlops.mdc`)
- Cursor command: [`.cursor/commands/check-parity.md`](.cursor/commands/check-parity.md) (alias intent of [`.claude/commands/check-parity.md`](.claude/commands/check-parity.md))
- Claude Code agents: [`.claude/agents/`](.claude/agents/) (use as **prompt references** in Cursor)
- Claude Code skills: [`.claude/skills/`](.claude/skills/)
- GitHub: [.github/agents/gcp-mlops-theme-research.agent.md](.github/agents/gcp-mlops-theme-research.agent.md)
- GitHub skill: [.github/skills/phase-doc-sync/SKILL.md](.github/skills/phase-doc-sync/SKILL.md)

Use them when tasks match their scope; otherwise follow this AGENTS guide and phase-local instructions.
