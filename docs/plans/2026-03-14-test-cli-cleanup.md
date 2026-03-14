# Implementation Plan: Test CLI Cleanup (FLI-93 + FLI-94)

## Issues
- FLI-93: test(cli): rename latam error test to mirror fast-variant naming pattern
- FLI-94: test(cli): migrate older search error tests to assert on result.stderr

## Research Context

All changes are in `tests/test_cli.py`. Five test functions are involved:

| Line | Current Name | Asserts On |
|------|-------------|------------|
| 764 | `test_search_error_displays_category` | `result.output` |
| 785 | `test_search_error_displays_hint` | `result.output` |
| 808 | `test_search_error_falls_back_to_category_hint` | `result.output` |
| 832 | `test_search_fast_error_displays_category_and_hint` | `result.stderr` ✓ |
| 857 | `test_search_error_displays_category_and_hint` | `result.stderr` ✓ |

The naming convention established by FLI-86 is `test_search_{provider}_error_*` where provider is `fast` or `latam`. Lines 832 and 857 already assert on `result.stderr` correctly.

The CliRunner uses default `mix_stderr=False` (Typer default), so stderr is already separated — the older tests just need their assertions pointed at `result.stderr`.

## Decisions Made

1. **Rename all four `test_search_error_*` functions (not just line 857)** to include `_latam_` prefix. FLI-93 explicitly mentions line 857, but since FLI-94 already touches the other three tests, renaming them in the same pass is the consistent thing to do. No extra risk since we're already modifying those functions.

2. **Keep `result.output.lower()` as `result.stderr.lower()`** — the `.lower()` in `test_search_error_falls_back_to_category_hint` is intentional (case-insensitive check on "circuit breaker"), so preserve it when switching to stderr.

## Implementation Tasks

1. **Rename line 857 test** — `test_search_error_displays_category_and_hint` → `test_search_latam_error_displays_category_and_hint` (FLI-93)
2. **Rename line 764 test** — `test_search_error_displays_category` → `test_search_latam_error_displays_category`
3. **Rename line 785 test** — `test_search_error_displays_hint` → `test_search_latam_error_displays_hint`
4. **Rename line 808 test** — `test_search_error_falls_back_to_category_hint` → `test_search_latam_error_falls_back_to_category_hint`
5. **Migrate line 764 assertions** — `result.output` → `result.stderr` in `test_search_latam_error_displays_category` (FLI-94)
6. **Migrate line 785 assertions** — `result.output` → `result.stderr` in `test_search_latam_error_displays_hint` (FLI-94)
7. **Migrate line 808 assertions** — `result.output` → `result.stderr` (preserving `.lower()`) in `test_search_latam_error_falls_back_to_category_hint` (FLI-94)

All changes in: `tests/test_cli.py`

## Acceptance Criteria
- All `test_search_error_*` functions renamed to `test_search_latam_error_*`
- All latam error tests assert on `result.stderr` instead of `result.output`
- Naming pattern matches the `test_search_fast_error_*` convention from FLI-86
- All tests pass

## Verification
```bash
uv run pytest tests/test_cli.py -k "test_search_latam_error or test_search_fast_error" -v
uv run pytest tests/test_cli.py -v
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-93`, `Closes FLI-94` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
