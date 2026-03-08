# LATAM Airlines BFF API — Reverse Engineering Analysis

**Captured:** 2026-03-08 16:29
**Route:** FOR → GRU (roundtrip), outbound 2026-04-12, inbound 2026-04-17

---

## The Search Endpoint

```
GET https://www.latamairlines.com/bff/air-offers/v2/offers/search
```

### Query Parameters

| Param | Example | Notes |
|---|---|---|
| `origin` | `FOR` | IATA code |
| `destination` | `GRU` | IATA code |
| `outFrom` | `2026-04-12` | Outbound date (YYYY-MM-DD) |
| `inFrom` | `2026-04-17` | Inbound date for roundtrip |
| `adult` | `1` | Passenger counts |
| `child` | `0` | |
| `infant` | `0` | |
| `cabinType` | `Economy` | `Economy`, `Business`, etc. |
| `redemption` | `false` | Miles redemption mode |
| `sort` | `RECOMMENDED` | `RECOMMENDED`, `CHEAPEST`, etc. |
| `locale` | `pt-br` | |
| `utm_*` | `undefined` | Optional, send as `undefined` |
| `inFlightDate` | `null` | Optional |
| `outFlightDate` | `null` | Optional |
| `outOfferId` | `null` | Optional |
| `inOfferId` | `null` | Optional |
| `kayakclickid` | `undefined` | Optional |
| `idMetasearch` | `undefined` | Optional |

### Required Request Headers

```
X-latam-Application-Country: BR
X-latam-Application-Lang: pt
X-latam-Application-Oc: br
X-latam-Client-Name: web-air-offers
X-latam-Track-Id: <random UUID>
X-latam-Request-Id: <random UUID>
X-latam-App-Session-Id: <random UUID>
x-latam-device-width: 1122
X-latam-Action-Name: search-result.flightselection.offers-search
X-latam-Application-Name: web-air-offers
x-latam-search-token: <HS512 JWT — see below>
x-latam-captcha-token: <reCAPTCHA Enterprise token — see below>
Referer: https://www.latamairlines.com/br/pt/oferta-voos?...
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
```

---

## Response Structure

Returns paginated flight offers. 50 results per page. Each entry in `content[]`:

```json
{
  "summary": {
    "tags": ["RECOMMENDED", "CHEAPEST"],
    "stopOvers": 0,
    "duration": 215,
    "flightCode": "LA3317",
    "origin": {
      "departure": "2026-04-12T02:45:00",
      "departureTime": "2:45",
      "iataCode": "FOR",
      "airport": "Intl. Pinto Martins",
      "city": "Fortaleza"
    },
    "destination": {
      "arrival": "2026-04-12T06:20:00",
      "arrivalTime": "6:20",
      "iataCode": "GRU",
      "airport": "Guarulhos Intl.",
      "city": "São Paulo"
    },
    "brands": [
      {
        "id": "SL",
        "brandText": "LIGHT",
        "price": {
          "currency": "BRL",
          "amount": 1029.58,
          "displayAmount": " 1.029,58"
        }
      },
      {
        "id": "KM",
        "brandText": "STANDARD",
        "price": { "currency": "BRL", "amount": 1128.38 }
      },
      {
        "id": "KD",
        "brandText": "FULL",
        "price": { "currency": "BRL", "amount": 1180.63 }
      },
      {
        "id": "RY",
        "brandText": "PREMIUM ECONOMY",
        "price": { "currency": "BRL", "amount": 1191.08 }
      }
    ],
    "lowestPrice": { "currency": "BRL", "amount": 1029.58 },
    "flightOperators": ["LATAM Airlines Brasil"],
    "changeOfAirport": false,
    "isInterlinealFlight": false
  }
}
```

Full sample response saved at: `research/search_response.json`

---

## Anti-Bot Protection — The Three Blockers

### 1. Akamai Bot Manager (Hardest)

Cookies: `_abck`, `ak_bmsc`, `bm_sz`, `bm_sv`, `akavpau_CyberLatam`, `akavpau_latamairlines_BBB`

How it works:
- Before the search call, the Akamai sensor JS fires a POST to an obfuscated URL (e.g. `/e_7JqBGlv.../`) with a `sensor_data` blob — an encrypted browser fingerprint (mouse events, canvas, WebGL, timing).
- The response updates the `_abck` cookie. A validated session has `~0~` in the value; unvalidated has `~-1~`.
- All BFF requests are blocked with 403 without a valid `_abck` cookie.

**Confirmed:** Direct HTTP request without Akamai cookies → 403 "Access Denied" HTML page.

### 2. `x-latam-search-token` (HS512 JWT)

```
Algorithm: HS512
TTL: 20 minutes
Payload: { country, language, destination, origin, iat, exp }
```

- Generated entirely **client-side by LATAM's JS bundle** — no API endpoint returns it.
- Signed with a secret key embedded in the JS.
- LATAM's engineers are aware: the payload contains `"message": "Hi Hacker friend, if you need to see our offers out of our site, feel free to contact us and we will see how we can help you. Thank you."`
- The secret could be rotated per-deploy. Reverse-engineering it is fragile.

### 3. `x-latam-captcha-token` (reCAPTCHA Enterprise)

- **Site key:** `6LcWzLoiAAAAAGJqY_Qn6XCssS6v6mlGqNg0qa3b`
- Type: reCAPTCHA Enterprise v3 (silent, score-based)
- Token fetched from `/recaptcha/enterprise/reload` ~200ms before the search call fires.
- **Solvable** via paid CAPTCHA services: 2captcha, CapSolver, Anti-Captcha (~$0.001/solve, ~5-10s)

---

## Feasibility: Direct HTTP Replay

| Approach | Verdict |
|---|---|
| Raw `requests`/`httpx`/`net/http` | ❌ Blocked by Akamai (403) |
| `curl_cffi` with Chrome impersonation | ❌ Still missing Akamai cookie validation |
| Stolen session + fresh captcha token | ⚠️ Might work temporarily but Akamai cookies expire |
| Playwright/Puppeteer (stealth mode) | ✅ Best approach — handles all three blockers |
| Playwright + network interception | ✅ **Recommended** — browser does auth, you capture the JSON |

---

## Recommended Implementation Strategy

### Option A: Playwright + Network Interception (Recommended)

Run a real Chromium browser. Let it load the LATAM search page normally. Intercept the `/bff/air-offers/v2/offers/search` response. Extract the JSON. No need to reverse-engineer tokens.

```python
from playwright.sync_api import sync_playwright
import json

def search_flights(origin, destination, outbound, inbound):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=False initially
        page = browser.new_page()

        results = {}

        def on_response(response):
            if 'bff/air-offers/v2/offers/search' in response.url:
                try:
                    results['data'] = response.json()
                except:
                    pass

        page.on('response', on_response)

        url = (
            f"https://www.latamairlines.com/br/pt/oferta-voos"
            f"?origin={origin}&outbound={outbound}T00:00:00.000Z"
            f"&destination={destination}&adt=1&chd=0&inf=0"
            f"&trip=RT&cabin=Economy&redemption=false&sort=RECOMMENDED"
            f"&inbound={inbound}T00:00:00.000Z"
        )

        page.goto(url)
        page.wait_for_response(lambda r: 'bff/air-offers/v2/offers/search' in r.url, timeout=30000)

        return results.get('data')
```

### Option B: Amadeus API (Zero Anti-Bot Friction)

LATAM (`LA`) is in the Amadeus GDS. Free tier available. Standard REST API with OAuth2.

- Docs: https://developers.amadeus.com/self-service/category/flights/api-doc/flight-offers-search
- Python SDK: `pip install amadeus`
- May miss LATAM-exclusive promo fares not published to GDS

---

## Other BFF Endpoints Observed

| Endpoint | Purpose |
|---|---|
| `GET /bff/air-offers/v2/offers/search` | **Main search** — flight availability + prices |
| `GET /bff/offer-creditcards/v1/featureFlags` | Credit card offer flags (cosmetic, not needed) |
