# Implementation Plan: Code Cleanup (FLI-88, FLI-89)

## Issues
- FLI-88: Guard Response import under TYPE_CHECKING in latam_scraper.py
- FLI-89: Use 'raise ... from None' in parse_date for cleaner CLI error output

## Research Context

### FLI-88
`Response` from `patchright.sync_api` is imported at line 10 of `src/flight_watcher/latam_scraper.py` but only used in the type annotation at line 57: `Callable[[Response], None]`. The codebase already has a `TYPE_CHECKING` pattern in `src/flight_watcher/cli/search.py`:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from flight_watcher.models import SearchResult
```

### FLI-89
`src/flight_watcher/cli/validators.py` line 26 raises `typer.BadParameter` inside `except ValueError` without suppressing the chain. Adding `from None` cleans up the traceback. Existing tests verify error message content only — `from None` won't affect them.

## Decisions Made
- FLI-88: Import `TYPE_CHECKING` from `typing`, add string annotation for `Response` in the `Callable` type hint (since the import won't be available at runtime). Keep `sync_playwright` on the runtime import line.
- FLI-89: Simple `from None` addition.

## Implementation Tasks
1. **FLI-88** — `src/flight_watcher/latam_scraper.py`
   - Add `from __future__ import annotations` at top (enables PEP 604 string annotations, avoids quoting `Response` manually)
   - Move `Response` import into `if TYPE_CHECKING:` block
   - Keep `sync_playwright` on the existing runtime import line

2. **FLI-89** — `src/flight_watcher/cli/validators.py`
   - Change line 26: `raise typer.BadParameter(...)` → `raise typer.BadParameter(...) from None`

## Acceptance Criteria
- `Response` is only imported at type-checking time
- `from __future__ import annotations` is present in latam_scraper.py
- `parse_date` uses `raise ... from None` in the ValueError handler
- All existing tests pass
- No runtime behavior changes

## Verification
```bash
uv run pytest tests/ -x -q
uv run mypy src/
uv run ruff check src/
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-88`, `Closes FLI-89` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
