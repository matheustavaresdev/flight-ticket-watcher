#!/bin/bash
set -euo pipefail

# PreCompact hook: injects current skill state into compacted context
# so the agent doesn't lose track of fix iterations, plan path, or PR URL.

BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
SHORT_BRANCH=$(echo "$BRANCH" | sed 's|^feature/||')
REVIEW_DIR=".reviews/${SHORT_BRANCH}"

# Count fix iterations
MANIFESTS=$(find "$REVIEW_DIR" -maxdepth 1 -name 'fix-manifest-*.md' 2>/dev/null | wc -l | tr -d ' ')

# Find active plan
PLAN=$(find docs/plans -maxdepth 1 -name '*.md' -newer .git/HEAD 2>/dev/null | tail -1 || echo "none")
[ -z "$PLAN" ] && PLAN="none"

# Get PR URL
PR_URL=$(gh pr view --json url -q '.url' 2>/dev/null || echo "none")

STATE="Skill state at compaction — Branch: $BRANCH | Fix iterations completed: $MANIFESTS/3 | Plan: $PLAN | PR: $PR_URL"

jq -n --arg ctx "$STATE" '{
  "hookSpecificOutput": {
    "hookEventName": "PreCompact",
    "additionalContext": $ctx
  }
}'
