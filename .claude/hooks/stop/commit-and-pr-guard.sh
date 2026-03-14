#!/bin/bash
set -euo pipefail

# Stop hook: two-phase guard that runs every time Claude finishes responding.
#
# Phase 1 (direct action): If uncommitted or unpushed work exists on a feature
#   branch, commit and push it directly from the hook. No blocking needed —
#   work is saved even if Claude has no context budget left.
#
# Phase 2 (blocking): If a PR exists for the branch but the agent didn't
#   mention the PR URL in its last message, block the stop and tell Claude
#   to include it. This enforces PR URL visibility across all skills.

INPUT=$(cat)

# If we already forced Claude to continue once, let it go — prevents infinite loops
if [ "$(echo "$INPUT" | jq -r '.commit_guard_active // false')" = "true" ]; then
  exit 0
fi

# Only enforce in git repos on feature branches
BRANCH=$(git branch --show-current 2>/dev/null || echo "")
[ -z "$BRANCH" ] && exit 0
[ "$BRANCH" = "main" ] && exit 0
[ "$BRANCH" = "master" ] && exit 0

# --- Phase 1: Save uncommitted work (direct action, no blocking) ---

DIRTY=$(git status --short 2>/dev/null || echo "")
if [ -n "$DIRTY" ]; then
  git add -u 2>/dev/null || true
  git commit -m "wip: save progress (auto-committed by stop hook)" 2>/dev/null || true
fi

# Push if there are unpushed commits
UPSTREAM=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || echo "")
if [ -n "$UPSTREAM" ]; then
  UNPUSHED=$(git log "$UPSTREAM"..HEAD --oneline 2>/dev/null || echo "")
  if [ -n "$UNPUSHED" ]; then
    git push origin "$BRANCH" 2>/dev/null || true
  fi
fi

# --- Phase 2: Enforce PR URL in agent's response (blocking) ---

LAST_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // empty')

# Skip Phase 2 if agent is handing off to the next pipeline stage.
if echo "$LAST_MSG" | grep -qiE "Spawning /revise|Spawning /rebase|Handed off to /revise|Handed off to /rebase|spawning.*revise|spawning.*rebase"; then
  exit 0
fi

PR_URL=$(gh pr view --json url -q '.url' 2>/dev/null || echo "")

if [ -n "$PR_URL" ] && ! echo "$LAST_MSG" | grep -qF "$PR_URL"; then
  echo "You are on branch '$BRANCH' which has an open PR but you didn't include the PR URL in your response." >&2
  echo "PR URL: $PR_URL" >&2
  echo "Include this URL prominently in your final response before stopping." >&2
  exit 2
fi

exit 0
