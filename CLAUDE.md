## Flight Ticket Watcher

Automated flight ticket price monitoring system. Intercepts airline search APIs, stores results, and runs periodic price checks across multiple routes and dates.

**Initial target:** LATAM Airlines (latamairlines.com/br/pt)
**Goal:** Build automation that searches for tickets across multiple routes on a schedule, without requiring manual website visits.

## Decision-Making: Research First, Recommend, Don't Ask

When you encounter design decisions during implementation, **do NOT present a list of options and ask the user to pick**. Instead:

1. **Research** — Launch sub-agents to investigate the codebase, existing patterns, library ecosystems, and trade-offs
2. **Decide** — Based on the research, make a recommendation considering: codebase conventions, ecosystem standards, simplicity, and the project's needs
3. **Present** — State your decision with brief rationale, then proceed with implementation

**Only ask the user when:**
- The decision is irreversible and has significant architectural consequences
- Two options are genuinely equal after research and you can't find a tiebreaker
- The decision involves business logic / product behavior, not technical implementation

## Issue Tracking with Linear

This project uses **Linear** for issue tracking via the Linear CLI.

**Workspace:** TavApps | **Team:** flight-ticket-watcher | **Project:** flight-ticket-watcher

| Tool | Best for |
|---|---|
| Linear CLI | All issue operations: CRUD, search, deps, velocity analytics, batch ops |
| Linear GraphQL (curl) | Milestones, documents, initiatives (CLI gaps only) |

**Core workflow:**
- Use `linear issues list --assignee me --state "In Progress"` to find active work
- Use `linear issues list --state "Todo" --team FLI` to find queued work
- Use `linear issues update <ID> --state "In Progress"` before starting work
- Include issue identifiers in commit messages: `git commit -m "Fix bug (FLI-123)"`
- GitHub integration auto-transitions: PR open → In Progress, PR review → In Review, PR merge → Done

**Priority mapping:** 1=Urgent, 2=High, 3=Normal, 4=Low

**Key rules:**
- Linear replaces all other task tracking
- Use `linear` CLI for all issue operations
- Never create issues outside Linear for project work

## Worktrees & Git Workflow

### Worktree Location

All worktrees live under `.worktrees/{feature-name}/` inside the project root.

### Worktree Naming Convention

```bash
git worktree add .worktrees/FLI-{ID}-{short-name} -b feature/FLI-{ID}-{short-name}
```

### Branch Workflow

1. **Always sync main before creating feature branches:**
   ```bash
   git checkout main
   git pull --rebase origin main
   ```

2. **After squash-merging a PR, immediately sync local main:**
   ```bash
   git checkout main
   git pull --rebase origin main
   ```

3. **After rebasing a feature branch, force push with lease:**
   ```bash
   git push --force-with-lease origin feature/my-branch
   ```

## Secrets Management

- `.env` — plaintext secrets (gitignored)
- `.env.example` — variable template with no real values
- NEVER commit `.env` to git

## NEVER EVER DO

- NEVER publish passwords, API keys, tokens to git
- Before ANY commit: verify no secrets included
- NEVER commit `.env` to git
