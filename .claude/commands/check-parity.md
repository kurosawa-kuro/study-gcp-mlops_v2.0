---
description: "Run the feature-parity-checker agent for the 6-file invariant (Phase 7 canonical)."
argument-hint: "<feature-name> | <PR#> | <commit-range> | (empty for working-tree changes)"
---

Invoke the **feature-parity-checker** agent to verify the 6-file feature parity invariant for `$ARGUMENTS`.

Context: Phase 7 (`7/study-hybrid-search-gke/`) requires that any feature column change touches all 6 sites (Dataform / `build_ranker_features` / `FEATURE_COLS_RANKER` / TF `ranking_log.features` RECORD / `validate_feature_skew.sql` UNPIVOT / Vertex Feature Group). Otherwise training-serving skew leaks in.

Agent prompt to dispatch:

> Verify the 6-file feature parity invariant for: **$ARGUMENTS**
>
> If `$ARGUMENTS` is empty, check the working-tree diff (`git diff --name-only HEAD`).
> If `$ARGUMENTS` looks like a feature name (e.g. `walk_minutes_to_station`), grep for it in all 6 sites.
> If `$ARGUMENTS` is a commit range (e.g. `main..HEAD`), use `git diff --name-only`.
>
> Output the table + verdict per the agent's output format. If FAIL, list the missing edits in dependency order.
