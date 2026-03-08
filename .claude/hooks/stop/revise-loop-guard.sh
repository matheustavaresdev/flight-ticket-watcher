#!/bin/bash
set -euo pipefail

# Revise loop guard: blocks agent from stopping if 3 fix iterations ran
# but Linear tasks weren't created for remaining items.

INPUT=$(cat)
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')

# Prevent infinite loops — if we already blocked once, let it go
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  exit 0
fi

# Only enforce in git repos on feature branches
BRANCH=$(git branch --show-current 2>/dev/null || echo "")
[ -z "$BRANCH" ] && exit 0
[ "$BRANCH" = "main" ] && exit 0
[ "$BRANCH" = "master" ] && exit 0

SHORT_BRANCH=$(echo "$BRANCH" | sed 's|^feature/||')
REVIEW_DIR=".reviews/${SHORT_BRANCH}"

# Only enforce during /revise sessions (review directory must exist)
if [ ! -d "$REVIEW_DIR" ]; then
  exit 0
fi

# Count fix-manifest files (= completed iterations)
MANIFEST_COUNT=$(find "$REVIEW_DIR" -maxdepth 1 -name 'fix-manifest-*.md' 2>/dev/null | wc -l | tr -d ' ')

# If fewer than 3 iterations, no enforcement needed (early exit is allowed)
if [ "$MANIFEST_COUNT" -lt 3 ]; then
  exit 0
fi

# 3+ iterations exist — check if the latest manifest has remaining items
LATEST_MANIFEST=$(find "$REVIEW_DIR" -maxdepth 1 -name 'fix-manifest-*.md' | sort -V | tail -1)
if [ -z "$LATEST_MANIFEST" ]; then
  exit 0
fi

# Count items: lines starting with a number followed by a period (numbered list items)
REMAINING=$(grep -cE '^\s*[0-9]+\.' "$LATEST_MANIFEST" 2>/dev/null || echo "0")

if [ "$REMAINING" -eq 0 ]; then
  exit 0
fi

# Items remain after 3 iterations — check if agent created Linear tasks
LAST_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // empty')
if echo "$LAST_MSG" | grep -qiE "Linear Tasks Created|Linear tasks created|FLI-[0-9]+.*(Critical|Warning)"; then
  exit 0
fi

# Block: agent must run Step 7
echo "Fix loop completed 3 iterations with $REMAINING items remaining in $LATEST_MANIFEST." >&2
echo "You MUST run Step 7: create Linear sub-issues for each remaining Critical/Warning item before stopping." >&2
echo "After creating the tasks, include 'Linear Tasks Created' and the new issue IDs in your response." >&2
exit 2
