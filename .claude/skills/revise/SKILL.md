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

**CRITICAL — TWO-STEP PROCESS. DO NOT PIPE.**

Codex CLI cannot be piped (`|`) — it detects non-terminal stdout and changes argument parsing, causing failures. Use `--json` mode with file redirect, then extract with `jq` in a **separate** command.

**Hardcode the literal output path.** Do NOT use shell variables. Substitute actual values directly.

#### Discover correct syntax first

Before the first Codex run in a session, verify the CLI syntax is current:

```bash
codex exec review --help 2>&1 | head -30
```

Check that these flags still exist: `--base`, `--full-auto`, `--ephemeral`, `--json`, `-m`. If any flag has changed, adapt the command. If unsure about available models, run `codex exec review --help` or use the Context7 MCP tool (`resolve-library-id` → `get-library-docs` for "openai/codex") to look up current docs.

#### The command (substitute actual branch path):

```bash
# Step 1: Codex writes JSON events to temp file (MUST use file redirect, NOT pipe)
# IMPORTANT: capture stderr to a file — do NOT use 2>/dev/null
codex exec review \
  --base main \
  --full-auto \
  --ephemeral \
  --json \
  > ".reviews/ACTUAL-SHORT-BRANCH-HERE/codex-raw.jsonl" \
  2> ".reviews/ACTUAL-SHORT-BRANCH-HERE/codex-stderr.log"

CODEX_EXIT=$?

# Step 2: Extract review text from agent_message events (SEPARATE command, not piped)
jq -rs '[.[] | select(.item.type == "agent_message")] | map(.item.text) | join("\n\n")' \
  ".reviews/ACTUAL-SHORT-BRANCH-HERE/codex-raw.jsonl" \
  > ".reviews/ACTUAL-SHORT-BRANCH-HERE/codex-review.md" 2>/dev/null || true

# Step 3: Cleanup temp file (keep stderr log for debugging)
rm -f ".reviews/ACTUAL-SHORT-BRANCH-HERE/codex-raw.jsonl"

echo "codex exit: $CODEX_EXIT"
```

**Notes:**
- Do NOT pass `-m <model>` unless you know the exact model name. Codex uses its default model if omitted, which is usually correct.
- Do NOT redirect stderr to `/dev/null` — capture it to `codex-stderr.log` so failures can be diagnosed.

#### If Codex fails (non-zero exit)

**Do NOT just say "Codex failed" and move on.** Instead:

1. Read the stderr log: `.reviews/<SHORT_BRANCH>/codex-stderr.log`
2. Read the raw JSONL output (may contain partial results): `.reviews/<SHORT_BRANCH>/codex-raw.jsonl`
3. Diagnose the failure:
   - **Model not found:** Remove the `-m` flag or use a valid model name
   - **Flag not recognized:** Run `codex exec review --help` and adapt flags
   - **Auth/network error:** Note it and proceed without Codex review
   - **Partial output:** Extract whatever review text was produced before the failure
4. Retry ONCE with corrected flags. If the retry also fails, proceed without Codex review but include the error in the final report.

**For re-review iterations**, change filenames to `codex-raw-2.jsonl` / `codex-review-2.md`, etc.

## Step 5: Collect and Classify Findings

After both reviewers complete, read both output files.

### Build Fix Manifest

1. Parse `## Critical Issues` and `## Warnings` from both reviews
2. Deduplicate across both reviewers
3. Build fix manifest — numbered list with file paths
4. Write to `.reviews/<SHORT_BRANCH>/fix-manifest-<N>.md`

### Build Suggestions Manifest

Also parse `## Suggestions` sections from both reviews:

1. Parse all suggestions from both reviewers
2. Deduplicate across reviewers (same file + similar description = one item)
3. Write to `.reviews/<SHORT_BRANCH>/suggestions-manifest.md`

Suggestions manifest format:

```markdown
# Suggestions Manifest

## Suggestions
1. [FILE: flight_watcher/foo.py] <description of the suggestion> (Source: Opus/Codex)
2. [FILE: flight_watcher/bar.py] <description> (Source: Opus/Codex)

## Deferred Items
<Empty initially — populated after fix loop if fixer skipped items as "requires architectural change">

## Totals
- Suggestions: <count>
- Deferred: <count>
```

If zero suggestions from both reviewers, still create the file with empty sections — Step 7b needs it.

### Check if Fix Loop is Needed

If zero Critical AND zero Warning items: **skip to Step 7b** ("Clean review — no Critical or Warning items found"). The fix loop is not needed, but suggestions must still be captured.

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

Also update `suggestions-manifest.md` with any new suggestions from the re-review. Append new suggestions (deduplicated against existing ones) to the `## Suggestions` section.

### 6f. Check Progress

- **New count == 0:** Exit loop → Step 7b, then Step 8
- **New count < old count:** Continue (if iteration < 3)
- **New count >= old count:** Stop immediately → Step 7b, then Step 8

**After iteration 3:** remaining items → Step 7, then Step 7b, then Step 8. No items → Step 7b, then Step 8. Never attempt a 4th iteration.

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

## Step 7b: Capture Suggestions and Deferred Items

**Trigger:** This step ALWAYS runs, regardless of how the fix loop ended (or if it ran at all). It captures non-blocking review findings so they aren't lost in `.reviews/` files.

### Update Suggestions Manifest with Deferred Items

If the fix loop ran, scan all fixer sub-agent outputs for items marked "SKIPPED: requires architectural change" or similar deferral language. Append these to the `## Deferred Items` section of `suggestions-manifest.md`.

Also scan your own output and the review outputs for any language indicating deferred work: "follow-up", "out of scope", "leave for later", "future improvement", "tech debt". Add these as deferred items.

### Read and Check

Read `.reviews/<SHORT_BRANCH>/suggestions-manifest.md`. If it has zero suggestions AND zero deferred items, skip to Step 8.

### Ensure Label Exists

```bash
linear labels create "Review:Suggestion" --team FLI --color "#3B82F6" 2>/dev/null || true
```

### Create Sub-issues

For each suggestion or deferred item:
```bash
linear issues create "<short description from finding>" \
    --team FLI \
    --parent "FLI-<FIRST_ISSUE_ID>" \
    --description "Suggestion from automated code review of $(git branch --show-current).

**Review finding:** <full finding text>
**File:** <file path>
**Source:** <Opus/Codex/Fixer>
**PR:** $(gh pr view --json url -q '.url' 2>/dev/null || echo 'N/A')

_This is a suggestion, not a blocker. Triage and prioritize as needed._" \
    --priority low \
    --labels "Review:Suggestion" \
    --state "Backlog"
```

Print summary:
```
## Suggestion Tasks Created
- FLI-XXX: <title> (Suggestion)
- FLI-YYY: <title> (Deferred)
```

### Rationalization Prevention

| Thought | Rule |
|---------|------|
| "This suggestion isn't worth a ticket" | ALL suggestions become tickets. User triages later. |
| "I'll just note it in the report" | Notes in reports get lost. Linear tasks don't. |
| "There are too many suggestions" | Create them all. Bulk-close is easy; recreating lost context isn't. |
| "This is just a style preference" | Style preferences are valid suggestions. Create the ticket. |

## Step 8: Final Report + Check Mergeability

```bash
git fetch origin main
git merge-base --is-ancestor origin/main HEAD
```

### If branch is up to date — TERMINAL state

Print full report WITH PR URL. Include in the report:
- Suggestions: <count> (captured as Linear tasks)
- Deferred: <count> (captured as Linear tasks)

Stop and wait for user input.

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
