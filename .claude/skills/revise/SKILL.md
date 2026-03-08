---
name: revise
description: "Run parallel Opus + Codex code reviews, auto-fix Critical/Warning issues (up to 3 iterations), and create Linear tasks for remaining items. Writes findings to .reviews/<branch-name>/. Use after /work creates a PR, or manually after /rebase."
disable-model-invocation: true
---

# Revise — Parallel Code Review with Auto-Fix Loop

You are the review phase. Run two independent reviewers in parallel, collect their findings, and automatically fix Critical and Warning issues (up to 3 iterations). If issues remain after 3 fix attempts, create Linear tasks. The user only sees the final report.

## Step 1: Detect Argument & Context

**Only one valid input:** a plan file path ending in `.md` (e.g., `docs/plans/2026-03-01-fli-5.md`).

If no argument or an invalid argument is provided:
```
This skill requires a plan file path.
Usage: /revise docs/plans/2026-03-01-fli-5.md
```
Then stop.

Read the plan with the Read tool.

### Parse Context

```bash
BRANCH=$(git branch --show-current)
SHORT_BRANCH=$(echo "$BRANCH" | sed 's|^feature/||')
```

Extract all issue IDs from the plan's `## Issues` section (pattern: `FLI-\d+`).

Verify we're on a feature branch (not `main`). If on main, print an error and stop.

### Check PR

```bash
PR_URL=$(gh pr view --json url -q '.url' 2>/dev/null || echo "")
```

### Check for Previous Run (Re-run Resilience)

```bash
REVIEW_DIR=".reviews/${SHORT_BRANCH}"
EXISTING_MANIFESTS=$(ls "$REVIEW_DIR"/fix-manifest-*.md 2>/dev/null | wc -l | tr -d ' ')
```

If `fix-manifest-*.md` files already exist, a previous `/revise` run was interrupted. Record the count and skip to Step 4 to re-review.

## Step 2: Prepare Review Directory

```bash
REVIEW_DIR=".reviews/${SHORT_BRANCH}"
mkdir -p "$REVIEW_DIR"
```

## Step 3: Gather Diff Context

```bash
CHANGED_FILES=$(git diff --name-only main...HEAD)
git diff main...HEAD --stat
git log main..HEAD --oneline
```

## Step 4: Launch Both Reviewers in Parallel

Launch BOTH in a single message.

### (a) Opus Code Review Sub-agent

`subagent_type: "code-reviewer"`

Prompt template:

> You are a senior engineer performing a thorough code review of a feature branch.
>
> ## Context
>
> **Plan file content:**
> ```
> <paste full plan content here>
> ```
>
> **Branch:** `<BRANCH>`
> **Issue(s):** `<ISSUE_IDS>`
> **Files changed:** `<CHANGED_FILES list>`
>
> ## Your Task
>
> 1. Read every file listed above using the Read tool
> 2. Run the project's build and test commands to verify the implementation
> 3. Review each changed file against the plan's acceptance criteria
>
> ## What to Check
>
> **Correctness:**
> - Does the implementation satisfy ALL acceptance criteria from the plan?
> - Are there logic bugs, off-by-one errors, null/nil/None risks?
> - Are error paths handled correctly?
>
> **Security:**
> - Input validation and sanitization
> - No secrets in code or logs
> - Injection risks (SQL, command, XSS)
>
> **Code Quality:**
> - Clean, readable code following project conventions
> - Proper error handling
> - No dead code or unused imports
>
> **Test Coverage:**
> - Are new functions tested?
> - Are edge cases covered?
>
> **Scope:**
> - Does the implementation stay within the plan's scope?
> - Flag anything added beyond the plan
>
> ## Output
>
> Write findings to: `<REVIEW_DIR>/<opus-review-filename>`

### (b) Codex CLI Review

Run via Bash tool with `run_in_background: true`.

```bash
codex exec review \
  --base main \
  --full-auto \
  --ephemeral \
  -o ".reviews/ACTUAL-SHORT-BRANCH-HERE/codex-review.md"
```

If Codex fails or times out, note the failure but do not block.

## Step 5: Collect and Classify Findings

After both reviewers complete, read both output files.

### Build Fix Manifest

1. Parse `## Critical Issues` and `## Warnings` from both reviews
2. Deduplicate across both reviewers
3. Build fix manifest — numbered list with file paths
4. Write to `.reviews/<SHORT_BRANCH>/fix-manifest-<N>.md`

### Check if Fix Loop is Needed

If zero Critical AND zero Warning items: **skip to Step 8**.

## Step 6: Fix Loop

Fix Critical and Warning issues automatically, up to 3 iterations. Suggestions are never auto-fixed.

### 6a. Launch Fixer Sub-agent

`subagent_type: "fixer"`

### 6b. Verify Fixes

Run project build/test commands. If they fail, retry once; revert on 2nd failure.

### 6c. Commit and Push

```bash
git add <specific files>
git commit -m "fix(<scope>): address review findings iteration <N> (FLI-XX)"
git push origin $(git branch --show-current)
```

### 6d. Re-review

Launch both reviewers again with iteration-numbered output files.

### 6e. Classify New Findings

Write new fix manifest.

### 6f. Check Progress

- **New count == 0:** Exit loop → Step 8
- **New count < old count:** Continue (if iteration < 3)
- **New count >= old count:** Stop immediately → Step 8

**After iteration 3:** remaining items → Step 7. No items → Step 8. Never attempt a 4th iteration.

### Rationalization Prevention

| Thought | Rule |
|---------|------|
| "Let me try one more fix" | If >= 3 iterations, go to Step 7. If no progress, STOP. |
| "This suggestion is worth fixing too" | Suggestions are NEVER auto-fixed. |
| "The fixer missed something, I'll fix it myself" | Only the fixer sub-agent fixes. |
| "One more iteration might resolve everything" | If count >= old count, STOP. |

## Step 7: Create Linear Tasks for Remaining Issues

**Trigger:** Only when 3 iterations completed AND items remain.

### Ensure Labels Exist

```bash
linear labels create "Review:Critical" --team FLI --color "#DC2626" 2>/dev/null || true
linear labels create "Review:Warning" --team FLI --color "#F59E0B" 2>/dev/null || true
```

### Create Sub-issues

For each remaining item, create Linear sub-issues with appropriate labels and priority.

Print summary:
```
## Linear Tasks Created
- FLI-XXX: <title> (Critical)
- FLI-YYY: <title> (Warning)
```

## Step 8: Final Report + Check Mergeability

```bash
git fetch origin main
git merge-base --is-ancestor origin/main HEAD
```

### If branch is up to date — TERMINAL state

Print full report WITH PR URL. Stop and wait for user input.

### If branch is behind main — spawn /rebase

Print brief status (no PR URL), then:

```bash
MY_PANE=$TMUX_PANE
MY_SESSION=$(tmux display-message -t "$MY_PANE" -p '#{session_name}')

echo "Spawning /rebase to sync with main..."

REBASE_PANE=$(tmux new-window -dPF '#{pane_id}' -t "$MY_SESSION" -n "rebase-${BRANCH}") && \
    tmux send-keys -t "$REBASE_PANE" "ccd --model opus \"/rebase\"" Enter

tmux kill-pane -t "$MY_PANE"
```
