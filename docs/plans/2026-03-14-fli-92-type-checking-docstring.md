# Implementation Plan: Document TYPE_CHECKING annotation introspection caveat

## Issues
- FLI-92: Document TYPE_CHECKING annotation introspection caveat in _make_bff_intercept

## Research Context

**File:** `src/flight_watcher/latam_scraper.py`

The file uses `from __future__ import annotations` (line 3) and guards `Response` under `TYPE_CHECKING` (lines 15-16):
```python
if TYPE_CHECKING:
    from patchright.sync_api import Response
```

The function `_make_bff_intercept` (line 63) uses `Response` in its return type: `Callable[[Response], None]`. With PEP 563 deferred evaluation, this works fine for static analysis and at runtime (annotations are strings, never resolved). However, if someone called `typing.get_type_hints()` on this function, it would raise `NameError` because `Response` isn't in the runtime namespace.

Current docstring (line 64):
```python
"""Return a response handler that captures BFF offer data into *captured*."""
```

No framework introspects this private callback, and all tests pass. This is purely a documentation note for future readers.

## Decisions Made
- Add a `Note:` block to the existing docstring rather than an inline comment, since the caveat is about the function's type signature, not a specific line.
- Keep it concise — one sentence explaining the caveat and the workaround if ever needed.

## Implementation Tasks
1. Extend the docstring of `_make_bff_intercept` in `src/flight_watcher/latam_scraper.py:64` to include a note about the `TYPE_CHECKING` / `get_type_hints()` caveat.

## Acceptance Criteria
- The docstring on `_make_bff_intercept` documents that `Response` is only available under `TYPE_CHECKING` and that `typing.get_type_hints()` would require `localns={'Response': Response}`.
- No functional changes — existing tests continue to pass.

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-92-type-checking-caveat
python -m pytest tests/ -x -q
python -m mypy src/flight_watcher/latam_scraper.py --no-error-summary
python -m ruff check src/flight_watcher/latam_scraper.py
```

## Done Criteria
- [ ] Docstring updated with TYPE_CHECKING caveat note
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-92`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
