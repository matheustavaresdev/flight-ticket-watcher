---
name: rebase
description: "Use when a feature branch needs to sync with main, especially after parallel workers merged PRs. Safely rebases, force pushes, and reports the PR URL."
disable-model-invocation: true
---

# Safe Rebase from Main

Rebase the current feature branch onto the latest main.

## Context

- Current branch: !`git branch --show-current 2>&1`
- Current status: !`git status --short 2>&1`
- Commits ahead of main: !`git log main..HEAD --oneline 2>&1`

## Steps

### 1. Guard Rails

```bash
[ "$(git branch --show-current)" = "main" ] && echo "ERROR: Already on main." && exit 1
```

If there are uncommitted changes, stash them:
```bash
git stash push -m "rebase-autostash-$(date +%s)"
```

### 2. Fetch Latest Main

```bash
git fetch origin main
```

Do NOT checkout main — stay on the feature branch.

### 3. Check for Potential Conflicts

```bash
git diff --name-only main...HEAD
git diff --name-only origin/main...main 2>/dev/null
```

### 4. Rebase

```bash
git rebase origin/main
```

#### If conflicts occur:

For each conflicted file:

1. Show: `git diff --name-only --diff-filter=U`
2. Read each conflicted file
3. Resolve:
   - **Generated files** (compiled assets, lock files): regenerate after rebase
   - **Non-overlapping** (different functions in same file): merge both
   - **Overlapping** (same lines): keep BOTH versions, ask user which to keep
4. `git add <resolved-file>`
5. `git rebase --continue`
6. If too complex: `git rebase --abort` and report

### 5. Verify After Rebase

Run the project's build and test commands. Fix any issues before pushing.

### 6. Restore Stashed Changes

If stashed: `git stash pop`

### 7. Force Push with Lease

```bash
git push --force-with-lease origin $(git branch --show-current)
```

**NEVER use `--force`** — `--force-with-lease` protects against overwriting others' commits.

## Report Back

```bash
PR_URL=$(gh pr view --json url -q .url 2>/dev/null)
```

Print:
- How many commits were rebased
- Whether any conflicts were resolved
- Whether build + tests pass

Then print the PR URL prominently on its own line.

**Stop and wait for user input.**
