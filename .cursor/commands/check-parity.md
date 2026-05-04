---
description: "Run a feature parity check for the 6-file invariant (Phase 7 hybrid search)."
argument-hint: "<feature-name> | <PR#> | <commit-range> | (empty for working-tree changes)"
---

# /check-parity (Cursor)

Use this command when a change might touch **ranker / feature columns** in Phase 7 (`7/study-hybrid-search-gke/`).

**Invariant (6 files, same change set):**

1. `pipeline/data_job/dataform/features/property_features_daily.sqlx`
2. `ml/data/feature_engineering/ranker_features.py` → `build_ranker_features`
3. `ml/data/feature_engineering/schema.py` → `FEATURE_COLS_RANKER`
4. `infra/terraform/modules/data/main.tf` → `ranking_log.features` RECORD
5. `infra/sql/monitoring/validate_feature_skew.sql` → UNPIVOT
6. `infra/terraform/modules/vertex/main.tf` → `google_vertex_ai_feature_group_feature`

**Instruction to the agent**

Verify the 6-file feature parity invariant for: **$ARGUMENTS**

- If `$ARGUMENTS` is empty, use `git diff --name-only HEAD` (or `main..HEAD` if on a feature branch) to see what changed.
- If `$ARGUMENTS` looks like a feature column name, grep it across all 6 sites.
- If `$ARGUMENTS` is a commit range (e.g. `main..HEAD`), use `git diff --name-only` for that range.

Output: table of the 6 sites (present / missing), **PASS** or **FAIL**, and if FAIL, the ordered list of missing edits.

**Reference:** `.claude/agents/feature-parity-checker.agent.md`, `7/study-hybrid-search-gke/CLAUDE.md` (Feature parity invariant).
