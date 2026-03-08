# Implementation Plan: Set up Python project scaffold

## Issues
- FLI-1: Set up Python project scaffold

## Research Context

**Existing project state:**
- `.gitignore` already covers Python artifacts (`__pycache__/`, `.venv/`, `venv/`, `*.pyc`, `dist/`, `build/`)
- `CLAUDE.md` defines project conventions (Linear, worktrees, secrets)
- `research/` folder has API analysis docs and sample responses
- No Python files, no `pyproject.toml`, no `src/` directory exist yet

**Key constraints from issue:**
- `fast-flights` v3 must be installed from GitHub: `pip install git+https://github.com/AWeirdDev/flights.git`
- `patchright` needs post-install browser setup: `patchright install chromium`
- Package structure: `src/flight_watcher/`

## Decisions Made

- **Package manager:** Standard `pip` with `pyproject.toml` — the issue explicitly uses `pip install -e .` as acceptance criteria. No need for uv/poetry complexity at this stage.
- **Build backend:** `hatchling` — lightweight, modern, works well with src-layout. No unnecessary config.
- **Python version:** 3.12+ — modern, good performance, aligns with current ecosystem.
- **Project layout:** `src/flight_watcher/` as specified in the issue (src-layout prevents accidental imports from project root).
- **No extras:** No linting config, no test framework, no pre-commit — not in scope for this issue.

## Implementation Tasks

1. Create `pyproject.toml` with project metadata, dependencies (`fast-flights` from GitHub, `patchright`), and build system config (`hatchling`) — creates `pyproject.toml`
2. Create package structure with `__init__.py` — creates `src/flight_watcher/__init__.py`
3. Add `.python-version` file set to `3.12` — creates `.python-version`
4. Verify `.gitignore` has adequate Python coverage (already confirmed — no changes needed)
5. Create virtualenv, install in editable mode, and run acceptance checks

## Acceptance Criteria
- `pip install -e .` works from project root
- `python -c "from fast_flights import FlightQuery; print('ok')"` succeeds
- `python -c "from patchright.sync_api import sync_playwright; print('ok')"` succeeds

## Verification
```bash
# Create venv and install
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .

# Acceptance checks
python -c "from fast_flights import FlightQuery; print('ok')"
python -c "from patchright.sync_api import sync_playwright; print('ok')"

# Install browser for patchright
patchright install chromium
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] `pip install -e .` succeeds
- [ ] Both import checks pass
- [ ] PR created with `Closes FLI-1`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Adding linting, formatting, or pre-commit config
- Adding README or other docs
- Setting up CI/CD
