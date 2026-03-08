---
name: pm
description: "Find available Linear issues without blockers, identify parallel work opportunities, create worktrees, and launch tmux workers. Use when starting a work session to decide what to build next."
---

## Tool Rules

**NEVER use Linear MCP tools** (`mcp__linear__*`) — they return broken data and hang.

- **Standard queries** → Linear CLI (`linear issues list`, `linear search`, etc.)
- **CLI gaps** (parent filtering, date filtering, pagination) → `lin-gql`

# What's Next — Linear Work Planner

You are a project manager. Analyze the current Linear state, recommend parallel work groups, and launch the workers via tmux.

## Live Project State

### Open Issues (FLI Team)
!`linear issues list --team FLI --state "Backlog,Todo" --format detailed --output json -n 50 2>&1`

### Dependency Graph
!`linear deps --team FLI --output json 2>&1`

### Currently In Progress
!`linear issues list --team FLI --state "In Progress" --format compact -n 20 2>&1`

### In Review
!`linear issues list --team FLI --state "In Review" --format compact -n 20 2>&1`

### Existing Worktrees
!`git worktree list 2>&1`

## Analysis Process

### Step 1: Check Active Work

If there are issues "In Progress" or "In Review", present them first:
- Ask if the engineer wants to **continue existing work** or **pick new tasks**
- Flag any in-progress issues that have no worktree (may need one created)

### Step 2: Build Dependency Map

From the dependency graph JSON, build:
- `blockedBy[issue]` → list of issues that must complete first
- `blocks[issue]` → list of issues this one unblocks

### Step 3: Find Ready Issues

An issue is **ready** when ALL of these are true:
1. Not an epic/parent issue (skip issues that are pure containers)
2. State is "Backlog" or "Todo" (not already in progress)
3. All `blockedBy` dependencies are in "Done" or "Canceled" state
4. OR it has no blockers at all

### Step 4: Rank Ready Issues

Sort ready issues by:
1. **Priority** — P1 (Urgent) > P2 (High) > P3 (Normal) > P4 (Low)
2. **Unblocking power** — issues that `block` more downstream work rank higher
3. **State** — "Todo" > "Backlog" (Todo = explicitly queued for work)

### Step 5: Form Parallel Groups

Group ready issues that can run simultaneously:
- Issues modifying the **same files/modules** → same group, or flag rebase dependency
- Issues creating **new files only** → always safe to parallelize independently
- Tightly related issues (shared module, shared feature) → same group/worktree
- Sequential dependencies → separate groups, note merge order

## Output Format

### Recommended Parallel Groups

This is the **primary output** — present one block per group:

```
## Group A — <Theme Name>
Worktree: `<branch-name>` | Issues: FLI-XX, FLI-YY

| Issue | Summary |
|---|---|
| FLI-XX | <1-sentence description of what this issue does> |
| FLI-YY | <1-sentence description> |

<Why these are grouped together — shared module, related feature, new files only, etc.>
⚠️ <Any file conflict or rebase dependency with other groups — or "No conflicts.">

---

## Group B — <Theme Name>
Worktree: `<branch-name>` | Issue: FLI-ZZ

FLI-ZZ: <1-sentence description>

<Context — what this touches, why it's independent or dependent>
⚠️ Must rebase onto Group A after Group A merges (both touch `<module>`).
```

### Supporting Context

After the recommended groups, show:

**Ready to Work (No Blockers)** — issues not included in the groups but available:
- ID, title, priority, 1-line summary, what it unblocks

**Blocked Summary** — issues waiting on in-progress work, grouped by what blocks them

End with:
> Confirm which groups to launch (or "all"), and I'll create the worktrees and start the workers.

## After Confirmation

When the engineer confirms groups to launch, execute ALL of the following:

### 1. Sync Main
```bash
git checkout main && git pull --rebase origin main
```

### 2. Create Worktrees
For each confirmed group:
```bash
# Single issue:
git worktree add .worktrees/FLI-<ID>-<short-name> -b feature/FLI-<ID>-<short-name>

# Combined issues:
git worktree add .worktrees/FLI-<ID1>+<ID2>-<short-name> -b feature/FLI-<ID1>+<ID2>-<short-name>
```

### 3. Copy Gitignored Config Files
```bash
# For each worktree created:
[ -f .env ] && cp .env .worktrees/FLI-<ID>-<short-name>/
```

### 4. Update Linear Status
```bash
# For each issue, run in parallel:
linear issues update FLI-<ID> --state "In Progress"
```

### 5. Launch Workers via tmux

```bash
MY_SESSION=$(tmux display-message -p '#{session_name}')
BASE="$(pwd)/.worktrees"

# For each confirmed group:
PANE_A=$(tmux new-window -dPF '#{pane_id}' -t "$MY_SESSION" -n "prep-FLI-XX") && \
    tmux send-keys -t "$PANE_A" "cd $BASE/<branch-a> && ccd --model opus \"/prep FLI-XX FLI-YY\"" Enter
```

After launching, report which windows were created and which issues are in each.

**`/pm` stays alive** — it's the orchestrator. Do not close this pane.

## Parallel Work Rules

- Each task (or combined task group) MUST be in its own worktree
- Tasks modifying the same files/modules CANNOT run in parallel
- After parallel work completes, merge PRs one at a time (oldest first)
- If conflicts arise, the `/work` skill auto-spawns `/rebase` to resolve them

## Post-Merge: Combined Branch Cleanup

**Linear only auto-closes the first `FLI-\d+` from the branch name.** For combined branches, the `/work` skill adds `Closes FLI-XX` lines in the PR body to handle this.

After merging a combined-issue PR, verify all issues transitioned to Done:
```bash
linear issues get FLI-<ID> --format compact
```

## Clean Up After Merge
```bash
git worktree remove .worktrees/<name>
git branch -d <branch-name>
```

## Quick Reference

| Action | Command |
|---|---|
| List ready work | `linear issues list --team FLI --state "Backlog,Todo" -n 50` |
| See dependencies | `linear deps --team FLI` |
| Check blockers | `linear issues blocked-by FLI-<ID>` |
| Update status | `linear issues update FLI-<ID> --state "In Progress"` |
| Create worktree | `git worktree add .worktrees/FLI-<ID>-<name> -b feature/FLI-<ID>-<name>` |
| Launch worker | `tmux new-window -dPF '#{pane_id}' ...` → `ccd --model opus "/prep FLI-XX"` |
| List worktrees | `git worktree list` |
