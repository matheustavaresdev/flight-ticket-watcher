#!/bin/bash
set -euo pipefail

# PreToolUse hook (Bash matcher): intercepts `tmux kill-pane` commands and
# prepends a git commit+push so worktree work is never lost when skills
# hand off to the next phase via tmux.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only care about tmux kill-pane commands
if ! echo "$COMMAND" | grep -qE 'tmux\s+kill-pane'; then
  exit 0
fi

# Only enforce on feature branches
BRANCH=$(git branch --show-current 2>/dev/null || echo "")
[ -z "$BRANCH" ] && exit 0
[ "$BRANCH" = "main" ] && exit 0
[ "$BRANCH" = "master" ] && exit 0

# Check for uncommitted changes
DIRTY=$(git status --short 2>/dev/null || echo "")
if [ -n "$DIRTY" ]; then
  # Dirty tree: commit all + push, then kill pane
  SAVE_CMD="git add -A && { git commit -m 'wip: save progress before handoff' 2>/dev/null || git commit -m 'wip: save progress before handoff' --no-verify 2>/dev/null || true; } && git push origin \$(git branch --show-current) 2>/dev/null || true"
  MODIFIED_COMMAND="${SAVE_CMD}; ${COMMAND}"
  jq -n --arg cmd "$MODIFIED_COMMAND" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow",
      updatedInput: { command: $cmd }
    }
  }'
  exit 0
fi

# Clean tree: check for unpushed commits
UPSTREAM=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || echo "")
if [ -n "$UPSTREAM" ]; then
  UNPUSHED=$(git log "$UPSTREAM"..HEAD --oneline 2>/dev/null || echo "")
  if [ -n "$UNPUSHED" ]; then
    MODIFIED_COMMAND="git push origin \$(git branch --show-current) 2>/dev/null || true; ${COMMAND}"
    jq -n --arg cmd "$MODIFIED_COMMAND" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "allow",
        updatedInput: { command: $cmd }
      }
    }'
    exit 0
  fi
fi

exit 0
