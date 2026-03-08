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
```python
"""LATAM Airlines flight search via Patchright + BFF API interception."""

import json
import time
from datetime import datetime
from pathlib import Path
from patchright.sync_api import sync_playwright


def search_latam(
    origin: str,
    destination: str,
    outbound: str,  # YYYY-MM-DD
    inbound: str,   # YYYY-MM-DD
    headless: bool = False,
) -> dict | None:
    """
    Search LATAM flights by navigating to the search results page
    and intercepting the BFF API response.

    Returns the parsed JSON response or None if capture failed.
    """
    start = time.time()
    captured = {}

    def on_response(response):
        if "bff/air-offers/v2/offers/search" in response.url:
            try:
                captured["data"] = response.json()
                captured["status"] = response.status
            except Exception as e:
                captured["error"] = str(e)
                captured["status"] = response.status

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            channel="chrome",
        )
        page = browser.new_page(no_viewport=True)
        page.on("response", on_response)

        url = (
            f"https://www.latamairlines.com/br/pt/oferta-voos"
            f"?origin={origin}&destination={destination}"
            f"&outbound={outbound}T00:00:00.000Z"
            f"&inbound={inbound}T00:00:00.000Z"
            f"&adt=1&chd=0&inf=0&trip=RT&cabin=Economy"
            f"&redemption=false&sort=RECOMMENDED"
        )

        page.goto(url, wait_until="domcontentloaded")

        try:
            page.wait_for_response(
                lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                timeout=30_000,
            )
        except Exception as e:
            print(f"Timeout waiting for BFF response: {e}")

        browser.close()

    elapsed = time.time() - start
    print(f"Search completed in {elapsed:.1f}s")

    if "error" in captured:
        print(f"Response error: {captured['error']} (status {captured.get('status')})")
        return None

    return captured.get("data")


def parse_offers(data: dict) -> list[dict]:
    """
    Extract fare class details from the BFF response.

    Returns a list of simplified offer dicts with brand/price breakdown.
    """
    offers = []
    for item in data.get("content", []):
        summary = item.get("summary", {})
        offer = {
            "flight_code": summary.get("flightCode"),
            "origin": summary.get("origin", {}).get("iataCode"),
            "destination": summary.get("destination", {}).get("iataCode"),
            "departure": summary.get("origin", {}).get("departure"),
            "arrival": summary.get("destination", {}).get("arrival"),
            "duration_min": summary.get("duration"),
            "stops": summary.get("stopOvers", 0),
            "brands": [],
        }
        for brand in summary.get("brands", []):
            offer["brands"].append({
                "id": brand.get("id"),
                "name": brand.get("brandText"),
                "price": brand.get("price", {}).get("amount"),
                "currency": brand.get("price", {}).get("currency"),
                "fare_basis": brand.get("farebasis"),
            })
        offers.append(offer)
    return offers


def print_offers(offers: list[dict]) -> None:
    """Print offers in a human-readable format."""
    for i, offer in enumerate(offers, 1):
        brands_str = " | ".join(
            f"{b['name']}: {b['currency']} {b['price']:.2f}"
            for b in offer["brands"]
            if b["price"] is not None
        )
        stops_str = "direct" if offer["stops"] == 0 else f"{offer['stops']} stop(s)"
        print(
            f"{i:2d}. {offer['flight_code']}  "
            f"{offer['origin']}->{offer['destination']}  "
            f"{offer['departure']} ({offer['duration_min']}min, {stops_str})  "
            f"[{brands_str}]"
        )


def save_response(data: dict, origin: str, destination: str) -> Path:
    """Save raw JSON response to output/ directory."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = output_dir / f"latam-{origin}-{destination}-{timestamp}.json"
    filename.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Response saved to {filename}")
    return filename


if __name__ == "__main__":
    # Default test route: Fortaleza -> São Paulo, round trip
    ORIGIN = "FOR"
    DESTINATION = "GRU"
    OUTBOUND = "2026-04-12"
    INBOUND = "2026-04-17"

    print(f"Searching LATAM: {ORIGIN} -> {DESTINATION}")
    print(f"  Outbound: {OUTBOUND}  Inbound: {INBOUND}")
    print()

    data = search_latam(ORIGIN, DESTINATION, OUTBOUND, INBOUND)

    if data:
        save_response(data, ORIGIN, DESTINATION)
        offers = parse_offers(data)
        print(f"\nFound {len(offers)} flights:\n")
        print_offers(offers)

        # Feasibility assessment
        print(f"\n--- Feasibility Result ---")
        print(f"Total offers: {len(offers)}")
        has_brands = any(len(o['brands']) > 0 for o in offers)
        print(f"Has fare classes (brands): {has_brands}")
        if has_brands:
            brand_ids = set()
            for o in offers:
                for b in o['brands']:
                    brand_ids.add(b['id'])
            print(f"Brand IDs found: {sorted(brand_ids)}")
            print("STATUS: GREEN - Feasibility confirmed")
        else:
            print("STATUS: YELLOW - Response captured but no brand data")
    else:
        print("\nSTATUS: RED - Failed to capture BFF response")
```

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
