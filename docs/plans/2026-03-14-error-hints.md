# Implementation Plan: Actionable Error Hints + CLI Error Surfacing

## Issues
- FLI-49: Add actionable error hints to error categories
- FLI-75: Surface error_category and hint in CLI for failed roundtrip legs

## Research Context

### Current State
- `ErrorCategory` enum in `errors.py` has 4 categories: RATE_LIMITED, NETWORK_ERROR, PAGE_ERROR, BLOCKED
- `SearchResult` in `models.py` already has `hint: str | None` field and `failure()` accepts `hint=`
- scanner.py and latam_scraper.py already populate contextual hints like "wait for breaker reset", "retries exhausted", "BFF response not captured"
- CLI (`cli/search.py`) currently only displays `result.error` on failure — never shows `error_category` or `hint`
- All CLI error output uses `typer.echo(f"[WARN] ...", err=True)` pattern

### Architecture Constraints
- Display module is `display.py` — but error messages are printed inline in `cli/search.py` command functions
- CLI uses `[OK]`, `[WARN]`, `[FAIL]` tag prefixes
- `errors.py` already has a parallel dict pattern: `RETRY_STRATEGIES: dict[ErrorCategory, RetryStrategy]`

## Decisions Made
- **ERROR_HINTS location:** `errors.py` alongside RETRY_STRATEGIES — follows existing pattern of category→metadata dicts
- **Hint format:** Format-string style with `{origin}`, `{dest}`, `{date}` placeholders, formatted via `get_error_hint()` helper
- **CLI display:** Inline in `cli/search.py` — add a `_print_error()` helper within the module to avoid duplication across 5 error print sites. Not in `display.py` since error printing is CLI-specific (display.py handles data rendering)
- **Hint visual distinction:** Print hint on a separate indented line below the error: `    Hint: <actionable text>`. Keeps it scannable without adding color dependencies
- **Existing contextual hints vs category hints:** The `SearchResult.hint` field already carries contextual hints from scanner/scraper. The new `ERROR_HINTS` dict provides _default_ actionable guidance per category. Strategy: if `result.hint` is already set, display it; otherwise fall back to `get_error_hint(category, **context)`

## Implementation Tasks

### Task 1: Add ERROR_HINTS dict and get_error_hint() to errors.py
**File:** `src/flight_watcher/errors.py`

Add after `RETRY_STRATEGIES`:
```python
ERROR_HINTS: dict[ErrorCategory, str] = {
    ErrorCategory.RATE_LIMITED: (
        "Rate limited (429 or CAPTCHA). Circuit breaker will auto-retry after backoff. "
        "If persistent, consider increasing MIN_DELAY_SEC/MAX_DELAY_SEC."
    ),
    ErrorCategory.NETWORK_ERROR: (
        "Network issue (timeout/DNS/connection). Check internet connectivity. "
        "Retry: flight-watcher search {search_type} --origin {origin} --dest {dest} --date {date}"
    ),
    ErrorCategory.PAGE_ERROR: (
        "Page structure changed or element not found. The airline may have updated their UI. "
        "Check scraper selectors against current site."
    ),
    ErrorCategory.BLOCKED: (
        "Anti-bot block (403). Circuit breaker active — all searches paused. "
        "If persistent, browser fingerprint or IP may be flagged. "
        "Check: flight-watcher health"
    ),
}


def get_error_hint(
    category: ErrorCategory, **context: str
) -> str:
    """Return actionable hint for an error category, formatted with route context."""
    template = ERROR_HINTS[category]
    try:
        return template.format(**context)
    except KeyError:
        return template  # return unformatted if placeholders missing
```

### Task 2: Add _print_search_error() helper to cli/search.py
**File:** `src/flight_watcher/cli/search.py`

Add a module-level helper to avoid duplicating error display logic across 5 sites:
```python
def _print_search_error(label: str, result: "SearchResult") -> None:
    """Print a structured error message for a failed search result."""
    parts = [f"[WARN] {label}: {result.error}"]
    if result.error_category:
        parts[0] += f" (category={result.error_category.value})"
    typer.echo(" ".join(parts), err=True)
    hint = result.hint
    if not hint and result.error_category:
        from flight_watcher.errors import get_error_hint
        hint = get_error_hint(result.error_category)
    if hint:
        typer.echo(f"    Hint: {hint}", err=True)
```

### Task 3: Wire _print_search_error() into all failure paths in cli/search.py
**File:** `src/flight_watcher/cli/search.py`

Replace all 5 `typer.echo(f"[WARN] ... failed: {result.error}", err=True)` calls with `_print_search_error()`:

1. **Line 51-53** (latam outbound): `_print_search_error("Outbound search failed", outbound_result)`
2. **Line 59-60** (latam return): `_print_search_error("Return search failed", return_result)`
3. **Line 69-70** (latam one-way): `_print_search_error("Search failed", result)`
4. **Line 108-109** (fast outbound): `_print_search_error("Outbound search failed", outbound)`
5. **Line 110-111** (fast return): `_print_search_error("Return search failed", inbound)`
6. **Line 116-117** (fast one-way): `_print_search_error("Search failed", result)`

### Task 4: Add tests for get_error_hint()
**File:** `tests/test_errors.py`

Add tests:
- `test_get_error_hint_returns_hint_for_each_category` — all 4 categories return non-empty strings
- `test_get_error_hint_formats_context` — NETWORK_ERROR hint includes formatted origin/dest/date
- `test_get_error_hint_missing_context_returns_template` — gracefully handles missing placeholders

### Task 5: Add tests for _print_search_error() CLI output
**File:** `tests/test_cli.py`

Add tests:
- `test_search_error_displays_category` — verify `(category=...)` appears in stderr
- `test_search_error_displays_hint` — verify `Hint: ...` line appears in stderr
- `test_search_error_falls_back_to_category_hint` — when result.hint is None but error_category is set, default hint appears

## Acceptance Criteria
- Every ErrorCategory has an actionable hint in ERROR_HINTS
- Hints include specific CLI commands to retry when applicable (NETWORK_ERROR)
- Hints include what to check/investigate (PAGE_ERROR, BLOCKED)
- CLI renders hints distinctly from error messages (indented `Hint:` line)
- error_category is displayed in parentheses on the error line
- All 5+ error display sites in cli/search.py use the unified helper
- Existing contextual hints from SearchResult.hint take precedence over defaults

## Verification
```bash
# Unit tests
uv run pytest tests/test_errors.py tests/test_cli.py -v

# Full test suite
uv run pytest --tb=short

# Type check
uv run mypy src/flight_watcher/errors.py src/flight_watcher/cli/search.py

# Lint
uv run ruff check src/flight_watcher/errors.py src/flight_watcher/cli/search.py
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-49` and `Closes FLI-75`

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding color/rich formatting to CLI output
- Modifying orchestrator.py hint handling
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
