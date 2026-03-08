# Flight Pricing API Research & Comparison

_Research date: 2026-03-08_

---

## CRITICAL: Amadeus Self-Service Shutdown

**Amadeus announced it is shutting down the Self-Service API portal.** New registrations paused in March 2026, full decommission on **July 17, 2026**. API keys will be deactivated. Only the Enterprise portal (with enterprise pricing) remains. This eliminates Amadeus as a viable free/low-cost option for new projects.

---

## Comparison Table

| Criteria | Amadeus Self-Service | Duffel | Kiwi/Tequila | SerpAPI (Google Flights) | Skyscanner (RapidAPI) | AviationStack | FlightAware | AeroDataBox |
|---|---|---|---|---|---|---|---|---|
| **Primary Data** | Flight search, pricing, booking | Flight search, booking, NDC | Flight search, booking, virtual interlining | Google Flights scraping | Flight search (meta) | Flight tracking/status | Flight tracking/status | Flight tracking/status |
| **Pricing Model** | Free tier + pay-per-call | $3/order + 1% managed content | Free (affiliate model) | $0-275/mo by search volume | Free tier on RapidAPI | Free-$499/mo | Free-$1000/mo | $0.99-$150/mo |
| **Free Tier** | 2,000 searches/mo (DYING July 2026) | No free searches; $3/booking, excess search fee $0.005 | Free for affiliates; ~200 req limit reported | 250 searches/mo | Free tier available (limited) | 100 calls/mo | 500 calls/mo (personal only) | 600 calls/mo ($0.99) |
| **Rate Limits** | 40 TPS (prod), 1 req/100ms (test) | 1500:1 search-to-book ratio | Not publicly documented | 50-6000/hour by plan | Not publicly documented | Varies by plan | Varies by plan | Varies by plan |
| **Flight Pricing Data** | Yes - real-time fares | Yes - real-time fares | Yes - real-time fares | Yes - Google Flights prices | Yes - meta-search prices | **No** - tracking only | **No** - tracking only | **No** - tracking only |
| **Price History/Trends** | Flight Price Analysis API (AI-based) | No | No | Yes - `price_insights` with historical data, typical range, price level | No | No | No | No |
| **Fare Rules/Cancellation** | Yes - detailed via `include=detailed-fare-rules` | Yes - offer/order conditions (changes, refunds, penalties) | Limited | No - pricing only | No | N/A | N/A | N/A |
| **Baggage Info** | Yes | Yes | Yes | Yes (baggage price policy) | Limited | N/A | N/A | N/A |
| **Booking Capability** | Yes (Flight Create Orders) | Yes (full booking flow) | Yes (via Kiwi fulfillment) | No - search only | No - redirects to airlines | No | No | No |
| **Brazil Domestic (FOR, GRU, GIG, CNF, BSB)** | Yes - 400+ airlines including LATAM, GOL, Azul via GDS | Yes - LATAM, GOL (via Travelport), Azul (via Travelport) confirmed | Likely yes - 750+ carriers, virtual interlining; not explicitly confirmed | Yes - whatever Google Flights shows (includes all major BR carriers) | Yes - meta-search aggregates all | Tracking only | Tracking only | Tracking only |
| **LATAM Airlines** | Yes (Amadeus is a major GDS for LATAM) | Yes (confirmed, direct page) | Yes (part of 750+ carriers) | Yes (via Google Flights) | Yes (meta) | Tracking only | Tracking only | Tracking only |
| **GOL** | Yes | Yes (via Travelport) | Likely yes | Yes (via Google Flights) | Yes (meta) | Tracking only | Tracking only | Tracking only |
| **Azul** | Yes | Yes (via Travelport) | Likely yes | Yes (via Google Flights) | Yes (meta) | Tracking only | Tracking only | Tracking only |
| **NDC Content** | Limited in self-service | Yes - direct NDC connections | No (uses own aggregation) | N/A (scrapes Google) | N/A | N/A | N/A | N/A |
| **Cheapest Date Search** | Yes (Flight Cheapest Date API - cached) | No native API | Yes (flexible date search) | Yes (Google Flights calendar view) | No | No | No | No |
| **Multi-city** | Yes | Yes | Yes (NOMAD API) | Yes | Yes | No | No | No |

---

## Detailed Analysis by API

### 1. Amadeus Self-Service API

**Status: SHUTTING DOWN July 17, 2026**

- **Flight Offers Search**: Real-time search across 400+ airlines. 2,000 free requests/month.
- **Flight Offers Price**: Confirms final price + detailed fare rules. 3,000 free requests/month.
- **Flight Cheapest Date Search**: Returns cached cheapest fares across a date range. Good for "when should I fly?" scenarios.
- **Flight Price Analysis**: AI-based price analysis comparing to historical fares. Returns whether current price is typical, low, or high.
- **Trip Purpose Prediction**: ML model predicting business vs. leisure travel. Niche use case.
- **Fare rules**: Available via `include=detailed-fare-rules` parameter. Covers REFUND, EXCHANGE, REVALIDATION, REISSUE, REBOOK, CANCELLATION categories.
- **Brazil coverage**: Excellent. Amadeus is the dominant GDS in Latin America. All major Brazilian carriers (LATAM, GOL, Azul) are in GDS.
- **Paid pricing**: Transaction fees beyond free tier are not publicly listed; varies by volume/agreement.
- **Enterprise alternative**: Enterprise portal continues, but pricing is opaque and likely requires commercial agreement.

**Verdict**: Was the best option. Now dead for indie/startup use. If you can get an Enterprise deal, it remains the most complete solution.

### 2. Duffel API

**Status: Active, well-funded, growing**

- **Pricing**: $3.00 per confirmed booking + 1% of order value for managed content + $2.00 per ancillary. Excess search fee of $0.005/search beyond 1500:1 search-to-book ratio.
- **Free tier**: No free tier per se - you pay per booking. Searches are free up to the ratio limit (15,000 free searches per 10 bookings/month).
- **For a price watcher (no bookings)**: Problematic. If you never book, you'd burn through the search allowance quickly. At $0.005/search beyond the ratio, monitoring prices could cost money.
- **Fare rules**: Yes - offer conditions include change/refund policies and penalty amounts.
- **Brazil coverage**: Confirmed: LATAM, GOL (via Travelport), Azul (via Travelport). All three major Brazilian carriers supported.
- **NDC**: Yes, direct NDC connections to some airlines. Superior content for NDC-enabled carriers.
- **FX fee**: 2% on currency conversions.

**Verdict**: Best for building a booking platform. Poor fit for a pure price-monitoring tool due to search-to-book ratio enforcement. You'd need to book occasionally or pay the excess search fee.

### 3. Kiwi/Tequila API

**Status: Active, free for affiliates**

- **Pricing**: Free access to API for affiliates. Revenue model is based on bookings/commissions.
- **Coverage**: 750+ carriers including 150 ground carriers. Virtual interlining combines routes across carriers that don't normally codeshare.
- **Rate limits**: Not publicly documented; reports suggest ~200 requests limit on basic access.
- **Brazil coverage**: Not explicitly confirmed, but given 750+ carriers and Kiwi.com showing Brazilian routes, GOL/Azul/LATAM are likely included.
- **Fare rules**: Limited information available through the API.
- **Cheapest dates**: Available via flexible date search.
- **NOMAD API**: Unique feature for multi-city "anywhere" searches.

**Verdict**: Good free option for searching, but terms of service may restrict non-affiliate use (pure monitoring without driving bookings). Rate limits are unclear. Worth testing.

### 4. SerpAPI (Google Flights Scraping)

**Status: Active, reliable**

- **What it does**: Scrapes Google Flights and returns structured JSON. Not an airline API - it's a search engine scraper.
- **Pricing**: Free (250/mo), $25/mo (1,000), $75/mo (5,000), $150/mo (15,000), $275/mo (30,000).
- **Price history**: Yes! `price_insights` returns: `lowest_price`, `price_level` (low/typical/high), `typical_price_range`, and `price_history` (timestamped historical prices). This is the same data Google Flights shows in its "Price graph" feature.
- **Fare rules**: No - just prices, airlines, durations, layovers.
- **Brazil coverage**: Whatever Google Flights covers, which includes all major Brazilian carriers (LATAM, GOL, Azul) and routes.
- **Cheapest dates**: Yes, via Google Flights date flexibility features.
- **Baggage**: Yes, baggage price policy data available.
- **Booking**: No - search/price monitoring only.

**Verdict**: Best fit for a price watcher/monitoring tool. Structured Google Flights data with price history and trend analysis. $75/mo for 5,000 searches is reasonable for monitoring multiple routes daily. No booking required, no search-to-book ratio concerns.

### 5. Skyscanner API (RapidAPI)

**Status: Available via RapidAPI (unofficial wrappers like "sky-scrapper")**

- **Note**: Skyscanner's official API is a partner program requiring application. The RapidAPI versions are third-party scrapers.
- **Official API**: Requires partnership application through partners.skyscanner.net. Not open to all developers.
- **RapidAPI wrappers**: "sky-scrapper" and "skyscanner80" provide Skyscanner data. Free tier available with limited requests. Plans from Basic ($15/mo) upward.
- **Data**: Meta-search prices (not direct airline fares). Good for comparison but prices may differ from actual booking price.
- **Brazil coverage**: Yes - Skyscanner covers Brazilian routes.
- **Fare rules**: No.
- **Price history**: No.

**Verdict**: Unreliable long-term (third-party scrapers can break). Official API requires partnership. Not recommended as primary source.

### 6. AviationStack / FlightAware / AeroDataBox

**These are NOT flight pricing APIs.** They provide:

| API | Data Provided | Use Case |
|---|---|---|
| **AviationStack** | Real-time flight status, tracking, schedules, airport data | Flight tracking dashboards, delay monitoring |
| **FlightAware (AeroAPI)** | Real-time tracking, flight history, airport info | Operational aviation data, flight tracking |
| **AeroDataBox** | Flight status, schedules, delays, airport info | Budget-friendly flight tracking for small apps |

None provide fare/pricing data. Useful for complementary features (e.g., "is this flight frequently delayed?") but not for price watching.

### 7. ITA Matrix

**Status: No API - manual/scraping only**

- **What it is**: Google's internal flight search tool (acquired ITA Software). Power users use it for complex routing, fare class analysis, and finding hidden fares.
- **Power user features**: Calendar view for cheapest dates, routing codes for specific paths, fare class breakdowns.
- **Automation**: No official API. The API was discontinued after Google's acquisition. Scraping is possible (Playwright + BeautifulSoup) but Google actively blocks it (CAPTCHAs, rate limiting, IP blocks).
- **Open source scrapers**: Exist on GitHub (FlightScraper, ITAmatrix_price_scraper) but are fragile.
- **Fare rules**: Yes - ITA Matrix shows detailed fare rules, but only via the web UI.

**Verdict**: Not viable for automated price watching. Useful for manual research only.

---

## Recommendations for a Flight Price Watcher

### Primary: SerpAPI Google Flights

**Best fit for price monitoring without booking.**

- Structured Google Flights data (same prices users see)
- Price history and trend data built in (`price_insights`)
- No booking requirement or search-to-book ratio
- Covers all Brazilian domestic routes
- $75/mo for 5,000 searches = ~166 route-date combos checked daily
- Clean JSON output, well-documented

### Secondary/Complementary: Kiwi/Tequila

**Good free supplement.**

- Free for affiliates
- Virtual interlining can find routes others miss
- Flexible date search for cheapest dates
- Worth registering and testing Brazil coverage

### If Booking is Needed Later: Duffel

**Best booking API.**

- Clean API, well-documented
- Confirmed LATAM/GOL/Azul support
- Real fare rules and cancellation policies
- NDC content (better fares from some airlines)
- Only makes sense if you're actually selling tickets

### Avoid for This Use Case

- **Amadeus Self-Service**: Dying July 2026. Don't build on it.
- **Skyscanner RapidAPI**: Unofficial scrapers, unreliable.
- **ITA Matrix**: No API, anti-scraping measures.
- **AviationStack/FlightAware/AeroDataBox**: No pricing data (tracking only).

---

## Cost Projections for Price Monitoring

Assuming monitoring 20 route-date combinations, checked 4x daily = 80 searches/day = ~2,400/month:

| Option | Monthly Cost | Searches Included | Notes |
|---|---|---|---|
| SerpAPI Free | $0 | 250 | Only ~3 routes, 1x/day |
| SerpAPI Starter | $25 | 1,000 | ~12 routes, 3x/day |
| SerpAPI Developer | $75 | 5,000 | 20 routes, 8x/day (plenty) |
| SerpAPI Production | $150 | 15,000 | Scale to 50+ routes |
| Kiwi/Tequila | $0 | ~200? | Unclear limits, affiliate terms |
| Duffel (no bookings) | ~$12/mo | 2,400 at $0.005/search | Ratio exceeded immediately |

**Recommended starting point**: SerpAPI Developer plan ($75/mo) for comprehensive monitoring with price history data.
