---
name: work
description: "Use when executing an implementation plan for a Linear issue. Accepts a plan file path only (produced by /prep). Implements via sub-agents, creates a PR, and spawns /revise as needed."
disable-model-invocation: true
---

> **NEVER use Linear MCP tools** (`mcp__linear__*`). Use CLI or `lin-gql`. See `/linear` skill.

# Work — Implement & Ship

You are the implementation phase. **Do NOT research or re-plan.** Execute the plan exactly as written and ship it.

## Step 1: Detect Argument

**Only one valid input:** a plan file path ending in `.md` (e.g., `docs/plans/2026-03-01-fli-5.md`).

Read the plan with the Read tool, then go directly to Step 2.

**If called with a FLI-XX issue ID or no argument:**
```
This skill requires a plan file path. To start work:
  - Run /pm to analyze available issues and launch workers automatically
  - Or run /prep FLI-XX to research and create a plan first

/work only accepts plan paths produced by /prep.
```
Then stop. Do not attempt to research or plan.

## Step 2: Parse Issue IDs

Extract all issue IDs from the plan file's `## Issues` section. Pattern: `FLI-\d+`.

These IDs are used for commit messages, PR title, and Linear updates.

## Step 3: Implement (commit as you go)

Read the plan fully before writing any code. Follow it exactly. **Do not add scope beyond what the plan specifies.**

Delegate file writes and edits to sub-agents via the Agent tool:
- Use `subagent_type: "general-purpose"` for implementation tasks
- Group related tasks (e.g., "implement tasks 1–3 from the plan")
- Review sub-agent output before committing

**After each logical milestone** (not at the end — at each milestone):
```bash
# Run the project's build/test commands from the plan's Verification section
git add <specific files>
git commit -m "<type>(<scope>): <description> (FLI-XX)"
```

Commit format: `<type>(<scope>): <description> (FLI-XX)`

For multi-issue plans, reference the most relevant issue per commit.

Do NOT batch everything into one final commit.

## Step 4: Finalize — Push + PR

This step is NOT optional. Do NOT ask the user if they want a PR. Create it.

### 1. Final verification
Run the project's build/test/lint commands from the plan.

### 2. Push
```bash
git push -u origin $(git branch --show-current)
```

### 3. Create PR

**CRITICAL — Linear auto-close rules:**
- Linear only auto-closes the first `FLI-\d+` matched from the branch name
- For combined branches, only the first issue gets auto-closed
- You MUST add a `Closes FLI-XX` line for EVERY issue

```bash
gh pr create --title "<type>(<scope>): <title> (FLI-XX, FLI-YY)" --body "$(cat <<'PREOF'
## Summary
<1-3 bullet points of what was implemented>

## Changes
<list of files created/modified with brief description>

## Test plan
- [ ] Build passes
- [ ] Tests pass

## Follow-up Issues
<list any Linear issues created during review, or "None">

Closes FLI-XX
Closes FLI-YY

🤖 Generated with [Claude Code](https://claude.com/claude-code)
PREOF
)"
```

## Step 5: Spawn /revise and close self

After creating the PR, hand off to `/revise` for code review. **Do NOT print the PR URL** — you are mid-pipeline.

```bash
MY_PANE=$TMUX_PANE
MY_SESSION=$(tmux display-message -t "$MY_PANE" -p '#{session_name}')
PLAN_PATH="<plan file path from Step 1>"
BRANCH=$(git branch --show-current)

echo "Spawning /revise for code review..."

REVISE_PANE=$(tmux new-window -dPF '#{pane_id}' -t "$MY_SESSION" -n "revise-${BRANCH}") && \
    tmux send-keys -t "$REVISE_PANE" "ccd --model sonnet \"/revise $PLAN_PATH\"" Enter

tmux kill-pane -t "$MY_PANE"
```

**CRITICAL — after running the bash block above:**
- Do NOT print a summary of what was implemented
- Do NOT print the PR URL
- Your pane will be killed — any text after the bash block will never be seen
- If `kill-pane` fails, just say "Handed off to /revise." and stop

## Quick Reference

| Step | Action | Tool |
|---|---|---|
| Plan path arg | Read plan → implement | Read tool |
| Wrong arg | Print error, stop | — |
| Parse issues | Extract FLI-XX from plan `## Issues` section | — |
| Implement | Sub-agents per task batch | Agent tool (general-purpose) |
| Milestone commit | build + test + commit | Bash |
| Push + PR | `git push` + `gh pr create` | Bash |
| Hand off | Spawn `/revise`, close self | tmux |
