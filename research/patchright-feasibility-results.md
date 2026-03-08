# Patchright + LATAM BFF Feasibility Results

**Date:** 2026-03-08
**Issue:** FLI-3
**Route tested:** FOR → GRU, round trip 2026-04-12 / 2026-04-17

---

## Status: GREEN (headed mode)

Patchright successfully intercepts the LATAM BFF search API in headed mode with real Chrome. Full fare class breakdown is captured without any CAPTCHA or manual intervention.

---

## Results Summary

| Mode | Status | Time | Notes |
|---|---|---|---|
| Headed (`headless=False`) | ✅ GREEN | ~13.7s | 50 flights, all 4 brand IDs |
| Headless (`headless=True`) | ❌ RED | 45.9s (timeout) | Akamai blocked — no BFF response |

---

## Headed Mode Details

- **50 flight offers** returned for the test route
- **4 fare classes captured:** SL (LIGHT), KM (STANDARD), KD (FULL), RY (PREMIUM ECONOMY)
- **Sample prices (direct flights):**
  - LA3317: LIGHT BRL 1,029.58 | STANDARD BRL 1,128.38 | FULL BRL 1,180.63 | PREMIUM ECONOMY BRL 1,191.08
  - LA4679: LIGHT BRL 1,298.71 | STANDARD BRL 1,388.72 | FULL BRL 1,451.03 | PREMIUM ECONOMY BRL 1,460.55
- **No CAPTCHA challenge appeared** — reCAPTCHA v3 passed silently
- **No Akamai block** — headed Chrome with Patchright stealth passed cleanly
- Response saved to `output/latam-FOR-GRU-20260308-175918.json`

---

## API Fix Found

The plan specified `page.wait_for_response()` but Patchright uses `page.expect_response()` (context manager pattern). Fixed in implementation:

```python
# Correct Patchright API
with page.expect_response(
    lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
    timeout=30_000,
):
    page.goto(url, wait_until="domcontentloaded")
```

---

## Headless Mode Analysis

Headless timed out at 30s (45.9s total including timeout wait). LATAM never fired the BFF API request — Akamai likely blocked the page load before results were fetched. The browser opened a page but the JS search flow never triggered.

This matches the expected behavior: Akamai detects headless Chrome despite Patchright's CDP patches. Headed mode with `channel="chrome"` is required.

---

## Recommendations for Production

1. **Headed mode required** — Run on a machine with a display (or Xvfb on Linux). No headless option.
2. **Timing:** ~14s per search. For 10 routes: ~2.3 minutes total if sequential; parallelism would require multiple browser instances.
3. **Parallelism:** Could run 2–3 browser instances simultaneously since Akamai appears to allow multiple headed sessions. Test before scaling.
4. **Frequency:** Headed browser is too slow/heavy for high-frequency scanning (every 30min across many routes). Architecture recommendation: use fast-flights (Option A) for broad sweeps, Patchright only for fare class detail fetches on triggered routes.
5. **Chrome channel:** Must use `channel="chrome"` (real installed Chrome), not default Chromium.
6. **`no_viewport=True`:** Keep this — avoids fixed-viewport fingerprint detection.
7. **Infrastructure:** Needs a desktop environment. Cloud options: VNC-enabled VPS, GitHub Actions with display, or a dedicated home server.

---

## Architecture Fit (A+C Hybrid)

This confirms the hybrid strategy from the project memory:
- **Option A (fast-flights):** Broad price sweeps every 30min, no browser needed
- **Option C (Patchright):** Triggered on price drop events only, fetches fare class breakdown
- **Estimated browser sessions:** 2–5/day instead of 48+ — reduces compute and Akamai exposure
