# Implementation Plan: Fresh Browser Context Per Search + Request Fingerprint Rotation

## Issues
- FLI-32: Fresh browser context per search — create a new browser context (clean cookies, cache, localStorage) for every individual search
- FLI-36: Request fingerprint rotation — rotate viewport sizes, Accept-Language headers, and timezone between sessions

## Research Context

### Current State
`latam_scraper.py` creates a browser per search via `sync_playwright()` context manager, then calls `browser.new_page(no_viewport=True)` directly. There is no explicit `browser.new_context()` call — pages use the browser's default context, which means cookies and state leak between pages if the browser were reused (currently it's not, but there's no explicit isolation).

Three search functions exist: `search_latam()`, `search_latam_oneway()`, `search_latam_roundtrip()`. All follow the same pattern:
```python
with sync_playwright() as p:
    browser = p.chromium.launch(headless=headless, channel="chrome")
    page = browser.new_page(no_viewport=True)
    # ... search logic ...
    browser.close()
```

### Patchright Context API
Patchright (Playwright fork) supports `browser.new_context()` with these relevant parameters:
- `locale` — sets `Accept-Language` header automatically
- `timezone_id` — changes `navigator.timezone` and JS date handling
- `viewport` — sets window size (`{'width': 1920, 'height': 1080}`)
- `no_viewport` — uses native resolution (current approach)

**Important Patchright constraint:** Do NOT set custom `user_agent` — Patchright's default UA is already patched for stealth. Custom UA breaks the fingerprint consistency that Patchright maintains.

### Test Patterns
Tests use `@patch("flight_watcher.latam_scraper.sync_playwright")` with `_setup_roundtrip_mocks()` helper. Mock chain: `mock_pw → chromium.launch → browser → new_page → page`. Tests will need to add `browser.new_context()` in the mock chain.

## Decisions Made

1. **New module `browser_profiles.py`** — contains fingerprint pool and `get_random_profile()` function. Keeps `latam_scraper.py` focused on search logic. Simple module, not over-abstracted.

2. **Viewport rotation uses specific sizes from FLI-36** — `1920x1080`, `1366x768`, `1440x900`. When a viewport is selected, we pass it as `viewport={"width": w, "height": h}`. When no viewport rotation is desired, we keep `no_viewport=True` on the page (current behavior).

3. **Locale/timezone pairs are coupled** — a Brazilian user in São Paulo timezone should have `pt-BR` locale. We define coherent profile combinations rather than random mix-and-match. The profiles from FLI-36: `pt-BR` + `America/Fortaleza`, `pt-BR` + `America/Sao_Paulo`, `en-US` + `America/Sao_Paulo`.

4. **Context lifecycle: `browser.new_context()` → `context.new_page()` → search → `context.close()`** — explicit context per search, even though we also close the browser. This is the correct Playwright pattern for isolation.

5. **No `user_data_dir`** — fresh context every time (FLI-32 requirement). No cookie persistence. This is explicitly what the issue asks for.

6. **No env vars for toggling** — fingerprint rotation is always on. The profiles are simple enough that there's no reason to make them configurable. KISS.

## Implementation Tasks

### Task 1: Create `src/flight_watcher/browser_profiles.py`

New module with:

```python
"""Browser fingerprint profiles for anti-detection rotation."""

import random
from dataclasses import dataclass

@dataclass(frozen=True)
class BrowserProfile:
    locale: str
    timezone_id: str
    viewport_width: int
    viewport_height: int

# Coherent Brazilian user profiles
PROFILES: list[BrowserProfile] = [
    BrowserProfile(locale="pt-BR", timezone_id="America/Sao_Paulo", viewport_width=1920, viewport_height=1080),
    BrowserProfile(locale="pt-BR", timezone_id="America/Sao_Paulo", viewport_width=1366, viewport_height=768),
    BrowserProfile(locale="pt-BR", timezone_id="America/Sao_Paulo", viewport_width=1440, viewport_height=900),
    BrowserProfile(locale="pt-BR", timezone_id="America/Fortaleza", viewport_width=1920, viewport_height=1080),
    BrowserProfile(locale="pt-BR", timezone_id="America/Fortaleza", viewport_width=1366, viewport_height=768),
    BrowserProfile(locale="pt-BR", timezone_id="America/Fortaleza", viewport_width=1440, viewport_height=900),
    BrowserProfile(locale="en-US", timezone_id="America/Sao_Paulo", viewport_width=1920, viewport_height=1080),
    BrowserProfile(locale="en-US", timezone_id="America/Sao_Paulo", viewport_width=1366, viewport_height=768),
    BrowserProfile(locale="en-US", timezone_id="America/Sao_Paulo", viewport_width=1440, viewport_height=900),
]

def get_random_profile() -> BrowserProfile:
    """Select a random browser fingerprint profile."""
    return random.choice(PROFILES)
```

Affects: `src/flight_watcher/browser_profiles.py` (new file)

### Task 2: Update `latam_scraper.py` — extract context creation helper

Add a private helper `_create_context()` that:
1. Calls `get_random_profile()`
2. Creates `browser.new_context(locale=..., timezone_id=..., viewport=...)`
3. Creates `context.new_page()`
4. Logs the selected profile at DEBUG level
5. Returns `(context, page, profile)`

```python
def _create_context(browser):
    """Create an isolated browser context with a random fingerprint profile."""
    profile = get_random_profile()
    logger.debug(
        "Browser profile: locale=%s tz=%s viewport=%dx%d",
        profile.locale, profile.timezone_id,
        profile.viewport_width, profile.viewport_height,
    )
    context = browser.new_context(
        locale=profile.locale,
        timezone_id=profile.timezone_id,
        viewport={"width": profile.viewport_width, "height": profile.viewport_height},
    )
    page = context.new_page()
    return context, page
```

Affects: `src/flight_watcher/latam_scraper.py`

### Task 3: Update `search_latam()` to use context isolation

Change from:
```python
page = browser.new_page(no_viewport=True)
```
To:
```python
context, page = _create_context(browser)
```

Add `context.close()` before `browser.close()`.

Affects: `src/flight_watcher/latam_scraper.py` (lines 60-80)

### Task 4: Update `search_latam_oneway()` to use context isolation

Same pattern as Task 3.

Affects: `src/flight_watcher/latam_scraper.py` (lines 116-133)

### Task 5: Update `search_latam_roundtrip()` to use context isolation

Same pattern as Tasks 3-4, but with multiple close paths (error branches at lines 201, 233, 249, 275). Ensure `context.close()` is called in every exit path before `browser.close()`.

Affects: `src/flight_watcher/latam_scraper.py` (lines 181-275)

### Task 6: Create `tests/test_browser_profiles.py`

Tests for the new module:
- `test_get_random_profile_returns_browser_profile` — type check
- `test_all_profiles_have_valid_fields` — all profiles have non-empty locale, timezone, positive viewport dims
- `test_profiles_contain_expected_viewports` — verify 1920x1080, 1366x768, 1440x900 are all present
- `test_profiles_contain_expected_locales` — verify pt-BR and en-US present
- `test_profiles_contain_expected_timezones` — verify Sao_Paulo and Fortaleza present
- `test_get_random_profile_uses_random_choice` — mock `random.choice`, verify called with PROFILES

Affects: `tests/test_browser_profiles.py` (new file)

### Task 7: Update `tests/test_latam_scraper.py`

Update `_setup_roundtrip_mocks()` to include `browser.new_context()` in the mock chain:
- `mock_browser.new_context.return_value = mock_context`
- `mock_context.new_page.return_value = mock_page`
- `mock_context.close = MagicMock()`
- Remove `mock_browser.new_page` setup

Patch `flight_watcher.latam_scraper.get_random_profile` in all tests to return a fixed profile.

Update assertions: verify `context.close()` is called in all test paths (success and failure).

Affects: `tests/test_latam_scraper.py`

## Acceptance Criteria

From FLI-32:
- Every search creates a new browser context with clean cookies, cache, and localStorage
- No session reuse across searches
- Context is closed after each search completes

From FLI-36:
- Viewport sizes rotate between 1920x1080, 1366x768, 1440x900
- Accept-Language rotates between pt-BR, en-US (via locale parameter)
- Timezone rotates between America/Fortaleza, America/Sao_Paulo

## Verification

```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-32+36-anti-detection
python -m pytest tests/ -v
python -c "from flight_watcher.browser_profiles import get_random_profile; p = get_random_profile(); print(f'{p.locale} {p.timezone_id} {p.viewport_width}x{p.viewport_height}')"
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-32` and `Closes FLI-36` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- User-Agent rotation (Patchright handles this internally)
- Cookie persistence / user_data_dir
- reCAPTCHA solving integration
- Proxy rotation
