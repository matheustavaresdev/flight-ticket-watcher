# Implementation Plan: Patchright + LATAM BFF Feasibility Test

## Issues
- FLI-3: Option C: Patchright + LATAM BFF feasibility test

## Research Context

### Project State
- `src/flight_watcher/` has only `__init__.py` — this is the first real module
- `patchright` already declared in `pyproject.toml` dependencies
- Python 3.12+, hatchling build system
- Reference data: `research/search_response.json` (308KB sample), `research/latam-api-analysis.md`

### Patchright Key Findings
- **Version:** 1.58.2 (latest, actively maintained)
- **Import:** `from patchright.sync_api import sync_playwright` — 100% Playwright-compatible API
- **Response interception:** `page.on('response', callback)` + `page.wait_for_response()` work identically to Playwright
- **Stealth:** Patches CDP `Runtime.enable` leak that Akamai detects. Uses isolated ExecutionContexts for `page.evaluate()`
- **Browser:** Use Chrome (`channel="chrome"`), not Chromium — real Chrome fingerprint is less suspicious
- **Headed mode strongly recommended** for Akamai-protected sites (`headless=False`)
- **`no_viewport=True`** avoids fingerprint red flags from fixed viewport sizes
- **reCAPTCHA v3** is silent/score-based — in headed mode with real Chrome, it typically passes without manual intervention
- **Chromium-only** — Firefox/WebKit not supported

### LATAM Anti-Bot Layers
1. **Akamai Bot Manager** — `_abck` cookie via browser fingerprint. Patchright handles this by not leaking CDP signals.
2. **`x-latam-search-token`** — HS512 JWT generated client-side. Browser handles naturally.
3. **`x-latam-captcha-token`** — reCAPTCHA Enterprise v3 (silent). Should pass in headed mode.

### Response Structure (from `research/search_response.json`)
```
content[] → summary.brands[] → { id: "SL"|"KM"|"KD"|"RY", brandText: "LIGHT"|"STANDARD"|"FULL"|"PREMIUM ECONOMY", price: { amount, currency } }
```
Each content item has: `summary.flightCode`, `summary.origin/destination`, `summary.duration`, `summary.stopOvers`, `summary.lowestPrice`, plus `itinerary` details.

### Search URL Format
```
https://www.latamairlines.com/br/pt/oferta-voos
  ?origin=FOR&destination=GRU
  &outbound=2026-04-12T00:00:00.000Z&inbound=2026-04-17T00:00:00.000Z
  &adt=1&chd=0&inf=0&trip=RT&cabin=Economy&redemption=false&sort=RECOMMENDED
```

## Decisions Made

1. **Single module `latam_scraper.py`** — no separate browser wrapper module. This is a feasibility test; abstraction can come later if it works.
2. **Sync API** — simpler for a POC. Async can be added later if needed for parallelism.
3. **Chrome channel, headed mode** — best chance of bypassing Akamai.
4. **Save raw JSON + print parsed summary** — captures full response for analysis while showing human-readable output.
5. **No env vars or config for now** — hardcode sensible defaults. This is a feasibility test, not production code.
6. **Output directory: `output/`** — gitignored, for captured responses.
7. **CLI entry point via `__main__` pattern** — run with `python -m flight_watcher.latam_scraper` or as a script.

## Implementation Tasks

### Task 1: Install Patchright browser
Ensure Chrome browser is installed for Patchright.
```bash
# In the venv
pip install -e . && patchright install chrome
```

### Task 2: Create `src/flight_watcher/latam_scraper.py`
Affects: `src/flight_watcher/latam_scraper.py` (new file)

**Module structure:**
See `src/flight_watcher/latam_scraper.py` for the authoritative implementation.

Key functions:
- `search_latam(origin, destination, outbound, inbound, headless=False) -> dict | None`
- `parse_offers(data) -> list[dict]`
- `print_offers(offers) -> None`
- `save_response(data, origin, destination) -> Path`

### Task 3: Add `output/` to `.gitignore`
Affects: `.gitignore`

Add `output/` to gitignore so captured JSON responses aren't committed.

### Task 4: Run the feasibility test
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-3-patchright-latam
source .venv/bin/activate
python -m flight_watcher.latam_scraper
```

Observe:
- Does the page load without getting blocked?
- Does the BFF response get intercepted?
- Does the response contain `content[]` with `brands[]`?
- How long does it take?
- Any CAPTCHA or Akamai blocks?

### Task 5: Test headless mode
After headed mode works, modify the call to test `headless=True`:
```python
data = search_latam(ORIGIN, DESTINATION, OUTBOUND, INBOUND, headless=True)
```

Document whether headless mode also works or gets blocked.

### Task 6: Document results
Affects: `research/patchright-feasibility-results.md` (new file)

Write a short feasibility report:
- GREEN/YELLOW/RED status
- Timing (how long per search)
- Any blocks encountered
- Headed vs headless results
- Recommendations for production use

## Acceptance Criteria
- Successfully navigates LATAM search page without getting blocked
- Intercepts the BFF search response with status 200
- Response contains `content[]` with flight offers including `brands[]` with prices
- Can extract fare class details: brand ID (SL/KM/KD/RY), price, cabin type
- Document timing: how long does a full search take?
- Document any issues: CAPTCHA blocks, Akamai detection, etc.

## Verification
```bash
# Install dependencies + browser
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-3-patchright-latam
source .venv/bin/activate
pip install -e . && patchright install chrome

# Run feasibility test (headed mode)
python -m flight_watcher.latam_scraper

# Check output
ls output/latam-FOR-GRU-*.json
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Patchright + Chrome installed and working
- [ ] `latam_scraper.py` created with search, parse, and save functions
- [ ] Feasibility test run with results documented
- [ ] `output/` gitignored
- [ ] PR created with `Closes FLI-3`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- CAPTCHA solver integration (that's a separate issue if needed)
- Async API conversion
- Configuration/env var system
- Proxy rotation
