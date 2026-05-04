#!/usr/bin/env bash
# SessionStart hook: show the head of the current phase's TASKS.md so the
# user (and the model) start each session with the active sprint in mind.
#
# Resolution: walk up from $CLAUDE_PROJECT_DIR (set by Claude Code) looking
# for a phase root (a dir containing Makefile + pyproject.toml). If found,
# show the first 50 lines of TASKS.md (Phase 7 = docs/tasks/TASKS.md, others
# = docs/TASKS.md). If not in a phase, do nothing — silent on root sessions.
#
# This hook prints to stdout (visible to the user). It must be fast (<1s)
# and never block the session.

set -euo pipefail

# Read the JSON event from stdin (Claude Code sends it but we only need cwd).
input=$(cat 2>/dev/null || true)
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)
[ -z "$cwd" ] && cwd="${CLAUDE_PROJECT_DIR:-$PWD}"

# Walk up to find a phase root (Makefile + pyproject.toml).
dir="$cwd"
phase_root=""
while [ "$dir" != "/" ] && [ -n "$dir" ]; do
  if [ -f "$dir/Makefile" ] && [ -f "$dir/pyproject.toml" ]; then
    phase_root="$dir"
    break
  fi
  dir=$(dirname "$dir")
done

[ -z "$phase_root" ] && exit 0

# Phase 7 reorg: docs/tasks/TASKS.md. Phase 1-6 flat: docs/TASKS.md.
tasks_md=""
if [ -f "$phase_root/docs/tasks/TASKS.md" ]; then
  tasks_md="$phase_root/docs/tasks/TASKS.md"
elif [ -f "$phase_root/docs/TASKS.md" ]; then
  tasks_md="$phase_root/docs/TASKS.md"
fi

[ -z "$tasks_md" ] && exit 0

phase_name=$(basename "$phase_root")
printf '## Current sprint — %s (%s)\n\n' "$phase_name" "${tasks_md#$phase_root/}"
head -50 "$tasks_md"
