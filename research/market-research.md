# Flight Watcher — Market & Technical Research

**Date:** 2026-03-08

## Key Findings Summary

### Data Sources
- **SerpAPI (Google Flights)**: Best for monitoring. $75/mo for 5K searches. Price history included.
- **fast-flights (AWeirdDev/flights)**: 867-star Python lib. Reverse-engineers Google Flights Protobuf. Free, no API key.
- **Kiwi/Tequila API**: Free for affiliates. 750+ carriers. Virtual interlining.
- **Amadeus**: SHUTTING DOWN self-service July 2026. Enterprise only after that.
- **Duffel**: $3/booking + ratio enforcement. Best for booking, bad for monitoring-only.
- **Playwright + LATAM BFF**: Direct airline prices. See latam-api-analysis.md.

### Gaps in Existing Tools (Our Opportunity)
1. No tool tracks fare class + cancellation policy alongside price
2. No configurable multi-criteria alerts (price + duration + stops + flexibility)
3. No "book now, search later" advisor with fare rule awareness
4. No Brazilian domestic market-specific tool that's maintained
5. No webhook/API alerts — all consumer tools use email/push only
6. No Pareto-optimal flight selection

### Brazilian Airline Fare Rules
- **ANAC 24h rule**: Free cancellation within 24h if flight is 7+ days out
- **CDC 7-day rule**: Courts increasingly backing 7-day withdrawal for online purchases
- **GOL MAX**: 95% refundable, free cancel — best "hold" fare
- **LATAM Full/Top**: Flexible, higher price
- **Promo/Light fares**: Non-refundable, no changes

### Notification Intelligence
- Percentile-based (Going does -2.2 std dev)
- Tiered urgency: exceptional (<5th pctile), good (5-20th), drop (any decrease)
- Cooldown periods per route
- Departure proximity escalation (28-39 day sweet spot for domestic)

### Best Open Source Building Blocks
- `AWeirdDev/flights` (fast-flights): Google Flights data, no API key, actively maintained
- `danielzontaojeda/scraping_flight_data`: All 3 BR carriers (reference only, abandoned)
- `ipeaGIT/flightsbr`: Historical ANAC data for price baselines
- `jeancsil/flight-spy`: Architecture reference for scheduler + alerts

See individual research docs for full details.
