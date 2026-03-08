---
name: prep
description: "Use when starting work on one or more Linear issues. Fetches issue details, runs parallel codebase and domain research agents, writes a formal implementation plan, commits it, spawns a fresh /work session for implementation, and closes the current planning window."
disable-model-invocation: true
---

> **NEVER use Linear MCP tools** (`mcp__linear__*`). Use CLI or `lin-gql`. See `/linear` skill.

# Prep — Research, Explore, Plan

You are the research and planning phase. Your job is to fully understand the problem and produce a committed plan file. **Do NOT write any implementation code.** A fresh session will handle that.

## Step 1: Detect Issues

Parse all issue identifiers from the argument (e.g., `/prep FLI-30` or `/prep FLI-30 FLI-31 FLI-35`).

If no argument was passed, check for "In Progress" issues:
```bash
linear issues list --team FLI --state "In Progress" --format compact -n 10 2>&1
```

## Step 2: Fetch All Issues + Check Blockers

For each issue, fetch full details and relations **in parallel**:
```bash
linear issues get FLI-<ID> --format full 2>&1
linear issues dependencies FLI-<ID> 2>&1
linear issues blocked-by FLI-<ID> 2>&1
```

**If any issue has unresolved blockers:** warn the user and ask whether to proceed.

**Mark all issues as "In Progress"** if not already:
```bash
linear issues update FLI-<ID> --state "In Progress"
```

## Step 3: Parallel Research

Launch **all applicable agents in a single message** (do not wait between launches):

### Research Depth Decision

Before launching agents, classify the issue complexity from the issue description(s):

**Small** (config change, one-file fix, copy existing pattern, < 3 sentences in description):
- Skip Test Patterns agent entirely
- Codebase Exploration: `"medium"` thoroughness
- Architecture Context: `"quick"` thoroughness
- Domain Research: skip unless new technology

**Medium** (new handler, modify existing flow across 2-3 files):
- All agents at `"medium"` thoroughness

**Large** (new package, new integration, architectural change, 4+ files):
- Codebase Exploration: `"very thorough"` thoroughness
- All others: `"medium"` thoroughness
- Domain Research: launch if ANY external tech is referenced

### (a) Codebase Exploration Agent
`subagent_type: "Explore"` — thoroughness: per Research Depth Decision above

Prompt:
> Find all files, patterns, and conventions relevant to implementing `<ISSUE_TITLES>`. Include:
> - Every file mentioned in the issue descriptions
> - All files in related modules/packages
> - Existing patterns for similar features
> - Test patterns for relevant areas
> - Return: file paths, relevant code snippets, and pattern summaries

### (b) Architecture Context Agent
`subagent_type: "Explore"` — thoroughness: `"medium"`

Prompt:
> Read `CLAUDE.md` and any `docs/` files related to `<ISSUE_DOMAIN>`. Identify architectural constraints, conventions, and requirements that apply to these issues.

### (c) Test Patterns Agent
`subagent_type: "Explore"` — thoroughness: `"medium"`

Prompt:
> Examine test files to understand how tests are written for features similar to `<ISSUE_TITLES>`. Find:
> - Test file naming conventions and directory structure
> - How test fixtures and helpers are defined and reused
> - How mocking is done for external services
> - Representative test examples
> Return: concrete test patterns with code examples to follow

### (d) Domain Research Agent
Launch **only** when issues reference a library, external API, tool, protocol, or technology not already established in the codebase.

`subagent_type: "domain-researcher"`

Prompt:
> Research `<LIBRARY/TOOL>` for use in this project:
> - `mcp__plugin_context7_context7__resolve-library-id` + `get-library-docs` for library docs
> - `WebSearch` for best practices, gotchas, and version compatibility
> - `mcp__deepwiki__ask_question` for GitHub repo-specific questions
> Return: recommended version/import path, key API patterns, configuration approach, and known gotchas.

### Wait for all agents before proceeding.

## Step 4: Write Unified Implementation Plan

Write a single plan file covering all issues.

**Plan file location:** `docs/plans/<YYYY-MM-DD>-<slug>.md`
- Single issue: slug from issue title, e.g., `2026-03-01-fli-5-latam-api-capture.md`
- Multiple issues: slug from shared theme, e.g., `2026-03-01-price-monitoring.md`

**Plan structure:**

```markdown
# Implementation Plan: <ISSUE_TITLE(S)>

## Issues
- FLI-XX: <title>
- FLI-YY: <title>

## Research Context
<Summary of what all research agents found — codebase patterns, architecture constraints,
test patterns, domain knowledge. This section lets the implementing session skip re-research.>

## Decisions Made
<Design decisions resolved during research, with rationale. Do NOT present options — decisions only.>

## Implementation Tasks
Ordered list of concrete tasks:
1. <task> — affects `<file>`
2. <task> — affects `<file>`
...

## Acceptance Criteria
<Pulled from issue descriptions + any additional criteria identified during research>

## Verification
<Exact commands to verify completion — build, test, lint commands appropriate for the project's stack>

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-XX` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
```

## Step 5: Commit Plan

```bash
git add docs/plans/<filename>.md
git commit -m "plan(<scope>): implementation plan for FLI-XX (FLI-XX)"
```

## Step 6: Spawn Implementation Window + Close Self

```bash
MY_PANE=$TMUX_PANE
MY_SESSION=$(tmux display-message -t "$MY_PANE" -p '#{session_name}')
PLAN_PATH="docs/plans/<filename>.md"

WORK_PANE=$(tmux new-window -dPF '#{pane_id}' -t "$MY_SESSION" -n "work-FLI-XX") && \
    tmux send-keys -t "$WORK_PANE" "ccd --model sonnet \"/work $PLAN_PATH\"" Enter

tmux kill-pane -t "$MY_PANE"
```

## Quick Reference

| Step | Action |
|---|---|
| Parse args | Extract FLI-XX identifiers |
| Fetch issues | `linear issues get` + `linear issues dependencies` + `linear issues blocked-by` |
| Update status | `linear issues update FLI-XX --state "In Progress"` |
| Research | 3–4 agents in parallel (single message) |
| Write plan | `docs/plans/<date>-<slug>.md` |
| Commit | `git add + git commit` |
| Spawn impl | `tmux new-window` → `send-keys` with `ccd --model sonnet "/work <plan-path>"` |
| Close self | `tmux kill-pane -t "$TMUX_PANE"` |
