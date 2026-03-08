# FLI-5: Proper Return Flight Capture via Page Interaction

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix return flight capture by simulating the real LATAM user flow — load RT page, capture outbound BFF, click a flight card to trigger return BFF, capture both legs in one browser session.

**Architecture:** Replace `search_latam_roundtrip`'s two-page-load approach with a single-session flow that mirrors how a real user interacts with the LATAM search results page. The `search_latam` function gets a new sibling `search_latam_roundtrip_interactive` that handles the click-to-reveal-return flow.

**Tech Stack:** Python, Patchright (patched Playwright), pytest

---

## Context

### Why the current approach fails
`search_latam_roundtrip` makes two `search_latam` calls with swapped origin/destination and swapped dates. The second call produces a URL like `origin=MIA&destination=FOR&outbound=2026-07-03&inbound=2026-06-18` — where `inbound` precedes `outbound`. LATAM's BFF never responds to this invalid date combination, causing a 30s timeout.

### How LATAM actually works
1. User navigates to RT search URL
2. BFF fires once → returns outbound flights
3. User clicks an outbound flight card
4. BFF fires again → returns return flights
5. The return BFF call may include `outOfferId` param referencing the selected outbound

### Key unknowns (resolved in Task 1)
- CSS selector for clickable flight cards
- Whether clicking any card (cheapest) triggers the return BFF
- Exact parameters of the return BFF request

---

## Task 1: Discover flight card selectors and return BFF behavior

**Files:**
- Create: `scripts/discover_return_flow.py` (temporary diagnostic)

**Step 1: Write the discovery script**

```python
"""
Discover LATAM flight card selectors and return BFF request pattern.

Loads a RT search page, captures the outbound BFF response, takes a
screenshot, dumps the page HTML for selector analysis, then attempts
to click the first flight result to trigger the return BFF.
"""
import json
import time
from pathlib import Path
from patchright.sync_api import sync_playwright

ORIGIN = "FOR"
DESTINATION = "GRU"
OUTBOUND = "2026-04-12"
INBOUND = "2026-04-17"
OUTPUT_DIR = Path("output/discovery")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    responses = []

    def on_response(response):
        if "bff/air-offers/v2/offers/search" in response.url:
            try:
                data = response.json()
                responses.append({
                    "url": response.url,
                    "status": response.status,
                    "data": data,
                    "timestamp": time.time(),
                })
                print(f"  [BFF] status={response.status} offers={len(data.get('content', []))}")
            except Exception as e:
                print(f"  [BFF] status={response.status} error={e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        page = browser.new_page(no_viewport=True)
        page.on("response", on_response)

        url = (
            f"https://www.latamairlines.com/br/pt/oferta-voos"
            f"?origin={ORIGIN}&destination={DESTINATION}"
            f"&outbound={OUTBOUND}T00:00:00.000Z"
            f"&inbound={INBOUND}T00:00:00.000Z"
            f"&adt=1&chd=0&inf=0&trip=RT&cabin=Economy"
            f"&redemption=false&sort=RECOMMENDED"
        )

        print(f"Navigating to: {url}")
        try:
            with page.expect_response(
                lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                timeout=30_000,
            ):
                page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Timeout waiting for outbound BFF: {e}")
            browser.close()
            return

        print(f"\nOutbound BFF captured. Waiting for page to render...")
        page.wait_for_timeout(5000)

        # Screenshot the search results
        page.screenshot(path=str(OUTPUT_DIR / "search-results.png"), full_page=True)
        print(f"Screenshot saved to {OUTPUT_DIR / 'search-results.png'}")

        # Dump a section of the HTML to find flight card selectors
        # Try common selector patterns for flight cards
        candidate_selectors = [
            "[data-test*='flight']",
            "[data-testid*='flight']",
            "[class*='flight']",
            "[class*='FlightCard']",
            "[class*='flight-card']",
            "[class*='flightCard']",
            "[class*='offer']",
            "[data-test*='offer']",
            "[class*='OfferCard']",
            "li[class*='card']",
            "div[class*='card']",
            "button[class*='select']",
            "ol li",  # common list structure
        ]

        print(f"\n--- Selector Discovery ---")
        found_selectors = []
        for sel in candidate_selectors:
            count = page.locator(sel).count()
            if count > 0:
                print(f"  {sel}: {count} matches")
                found_selectors.append((sel, count))

        # If we found selectors, try clicking the first flight card
        if found_selectors:
            # Try the most specific selector first
            best_sel = found_selectors[0][0]
            print(f"\nAttempting to click first element matching: {best_sel}")

            pre_click_count = len(responses)
            try:
                page.locator(best_sel).first.click(timeout=5000)
                print("Click succeeded. Waiting for return BFF response...")

                # Wait for a second BFF response
                try:
                    page.wait_for_response(
                        lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                        timeout=15_000,
                    )
                    print("Return BFF response captured!")
                except Exception:
                    print("No return BFF response after click.")
            except Exception as e:
                print(f"Click failed: {e}")

            if len(responses) > pre_click_count:
                ret_resp = responses[-1]
                print(f"\nReturn BFF URL: {ret_resp['url']}")
                print(f"Return offers: {len(ret_resp['data'].get('content', []))}")

        # Save all captured responses
        for i, resp in enumerate(responses):
            fname = OUTPUT_DIR / f"bff-response-{i}.json"
            fname.write_text(json.dumps({
                "url": resp["url"],
                "status": resp["status"],
                "data": resp["data"],
            }, indent=2, ensure_ascii=False))
            print(f"Saved {fname}")

        # Dump page content for manual analysis
        html = page.content()
        (OUTPUT_DIR / "page.html").write_text(html)
        print(f"Page HTML saved to {OUTPUT_DIR / 'page.html'}")

        browser.close()

    print(f"\n--- Summary ---")
    print(f"Total BFF responses captured: {len(responses)}")
    for i, r in enumerate(responses):
        origin_iata = "?"
        content = r["data"].get("content", [])
        if content:
            origin_iata = content[0].get("summary", {}).get("origin", {}).get("iataCode", "?")
        print(f"  [{i}] {origin_iata}->... ({len(content)} offers)")


if __name__ == "__main__":
    main()
```

**Step 2: Run the discovery script**

Run: `python scripts/discover_return_flow.py`

Observe the output carefully:
- Which selectors match flight cards?
- Does clicking trigger a second BFF response?
- What does the return BFF URL look like?
- Take note of the screenshot at `output/discovery/search-results.png`

**Step 3: Analyze and document findings**

Read `output/discovery/bff-response-0.json` (outbound) and `bff-response-1.json` (return, if captured).
Read `output/discovery/search-results.png` to see the page layout.

If the click didn't work, inspect `output/discovery/page.html` for the actual DOM structure. Search for flight-related class names and data attributes. Iterate with different selectors until the return BFF fires.

**Do NOT proceed to Task 2 until you have:**
1. A confirmed CSS selector that clicks a flight card
2. A confirmed return BFF response captured
3. Understanding of the return BFF URL parameters

Document findings as comments in the commit message.

**Step 4: Commit discovery findings**

```bash
git add scripts/discover_return_flow.py
git commit -m "chore: add discovery script for return flight selectors (FLI-5)

Findings:
- Flight card selector: <FILL IN>
- Return BFF triggered: yes/no
- Return BFF URL params: <FILL IN>"
```

---

## Task 2: Implement `search_latam_roundtrip` with page interaction

**Files:**
- Modify: `src/flight_watcher/latam_scraper.py`

**Step 1: Write the failing test**

Add to `tests/test_latam_scraper.py`:

```python
@patch("src.flight_watcher.latam_scraper.sync_playwright")
def test_roundtrip_interactive_captures_both_legs(mock_pw):
    """Verify the interactive roundtrip flow: load page, capture outbound,
    click flight card, capture return."""
    outbound_resp = _make_bff_response("FOR", "GRU", brand_price=1000.0)
    return_resp = _make_bff_response("GRU", "FOR", brand_price=1200.0)

    # Build mock browser/page chain
    mock_browser = MagicMock()
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser

    # Track the on_response callback
    captured_callback = {}
    def fake_on(event, cb):
        captured_callback[event] = cb
    mock_page.on = fake_on

    # Mock expect_response as context manager (outbound BFF)
    mock_page.expect_response.return_value.__enter__ = MagicMock()
    mock_page.expect_response.return_value.__exit__ = MagicMock(return_value=False)

    # Mock locator for flight card click
    mock_locator = MagicMock()
    mock_page.locator.return_value = mock_locator
    mock_first = MagicMock()
    mock_locator.first = mock_first

    # Mock wait_for_response for return BFF
    mock_page.wait_for_response.return_value = MagicMock()

    # The function under test will register on_response, then we simulate
    # the BFF responses being captured
    # ... (exact mock wiring depends on Task 1 findings)

    # For now, test the contract: function returns (outbound, return) tuple
    # and the page interaction sequence is: goto -> wait -> click -> wait
```

**Note:** The exact mock structure depends on Task 1 findings (selector, timing). Update the test after Task 1.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_latam_scraper.py -v -k "interactive"`
Expected: FAIL

**Step 3: Implement the interactive roundtrip function**

Replace `search_latam_roundtrip` in `latam_scraper.py` with a single-session flow:

```python
def search_latam_roundtrip(
    origin: str,
    destination: str,
    outbound: str,
    inbound: str,
    headless: bool = False,
    flight_card_selector: str = "<FROM TASK 1>",
) -> tuple[dict | None, dict | None]:
    """
    Search LATAM round-trip flights in a single browser session.

    Flow:
    1. Navigate to RT search URL
    2. Capture outbound BFF response
    3. Click the first (cheapest) flight card
    4. Capture return BFF response

    Returns (outbound_data, return_data). Either may be None.
    """
    start = time.time()
    outbound_data = None
    return_data = None
    bff_responses = []

    def on_response(response):
        if "bff/air-offers/v2/offers/search" in response.url:
            try:
                data = response.json()
                if response.status == 200:
                    bff_responses.append(data)
            except Exception as e:
                print(f"BFF response error: {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, channel="chrome")
        page = browser.new_page(no_viewport=True)
        page.on("response", on_response)

        url = _build_latam_url(origin, destination, outbound, inbound)

        # Step 1: Load RT search page and capture outbound BFF
        try:
            with page.expect_response(
                lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                timeout=30_000,
            ):
                page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Timeout waiting for outbound BFF: {e}")
            browser.close()
            elapsed = time.time() - start
            print(f"Search completed in {elapsed:.1f}s")
            return None, None

        if bff_responses:
            outbound_data = bff_responses[0]
            print(f"Outbound captured: {len(outbound_data.get('content', []))} offers")

        # Step 2: Wait for flight cards to render
        page.wait_for_timeout(3000)

        # Step 3: Click first flight card to trigger return BFF
        try:
            card = page.locator(flight_card_selector).first
            card.click(timeout=10_000)
            print("Clicked flight card, waiting for return BFF...")

            # Step 4: Wait for return BFF response
            page.wait_for_response(
                lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                timeout=15_000,
            )
        except Exception as e:
            print(f"Return flight capture failed: {e}")

        if len(bff_responses) >= 2:
            return_data = bff_responses[1]
            print(f"Return captured: {len(return_data.get('content', []))} offers")

        browser.close()

    elapsed = time.time() - start
    print(f"Search completed in {elapsed:.1f}s")
    return outbound_data, return_data
```

**Important:** Replace `<FROM TASK 1>` with the actual selector discovered in Task 1.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_latam_scraper.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/flight_watcher/latam_scraper.py tests/test_latam_scraper.py
git commit -m "feat(latam_scraper): single-session roundtrip with flight card click (FLI-5)"
```

---

## Task 3: Update tests for new roundtrip behavior

**Files:**
- Modify: `tests/test_latam_scraper.py`

**Step 1: Remove old roundtrip tests that assert the two-call pattern**

The existing tests `test_roundtrip_calls_search_latam_twice`, `test_roundtrip_returns_none_when_outbound_fails`, and `test_roundtrip_returns_none_return_when_return_fails` all mock `search_latam` as a standalone function call. Since `search_latam_roundtrip` no longer delegates to `search_latam`, these tests are invalid.

Replace them with tests that mock the Playwright browser directly:
1. `test_roundtrip_captures_both_legs` — happy path, both BFF responses arrive
2. `test_roundtrip_returns_none_when_outbound_times_out` — first BFF never arrives
3. `test_roundtrip_returns_none_return_when_click_fails` — click times out or no second BFF
4. `test_roundtrip_url_has_correct_dates` — verify the URL built for the RT page has correct outbound/inbound dates (not swapped)

**Step 2: Run tests**

Run: `pytest tests/test_latam_scraper.py -v`
Expected: all PASS

**Step 3: Commit**

```bash
git add tests/test_latam_scraper.py
git commit -m "test(latam_scraper): update roundtrip tests for interactive flow (FLI-5)"
```

---

## Task 4: Live verification

**Step 1: Run the script with a real search**

```bash
python scripts/find_cheapest.py FOR GRU 2026-04-12 2026-04-17
```

Expected: both outbound (FOR->GRU) and return (GRU->FOR) sections display with flight data, plus a round-trip summary.

**Step 2: Run with the user's original failing case**

```bash
python scripts/find_cheapest.py FOR MIA 2026-06-18 2026-07-03
```

Expected: both legs captured, no timeout.

**Step 3: Run one-way to verify no regression**

```bash
python scripts/find_cheapest.py FOR GRU 2026-04-12
```

Expected: one-way search works as before.

---

## Task 5: Clean up

**Step 1: Delete discovery script**

```bash
rm scripts/discover_return_flow.py
rm -rf output/discovery/
```

**Step 2: Commit**

```bash
git add -A
git commit -m "chore: remove discovery script (FLI-5)"
```

---

## Task 6: Full test suite and push

**Step 1: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: all PASS

**Step 2: Push and verify PR**

```bash
git push origin feature/FLI-4-return-flight
```

---

## Acceptance Criteria

- [ ] Flight card selector discovered and documented
- [ ] `search_latam_roundtrip` uses single browser session with click interaction
- [ ] Both outbound and return BFF responses captured in one session
- [ ] `find_cheapest.py FOR MIA 2026-06-18 2026-07-03` returns both legs
- [ ] `find_cheapest.py FOR GRU 2026-04-12` (one-way) still works
- [ ] All unit tests pass
- [ ] No regression in `search_latam` (unchanged)

## NOT in Scope

- Refactoring `find_cheapest.py` display logic
- Changing `_build_latam_url` signature
- Adding retry/resilience logic
- Supporting multiple flight card selection strategies
- Headless mode investigation
