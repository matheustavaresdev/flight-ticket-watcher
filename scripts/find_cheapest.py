"""Find the cheapest LATAM flight for a given route and dates."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.flight_watcher.latam_scraper import parse_offers, search_latam


def find_cheapest_flights(offers: list[dict], top_n: int = 5) -> list[dict]:
    """Sort offers by cheapest LIGHT tier price, return top N."""
    priced = []
    for offer in offers:
        light_prices = [b["price"] for b in offer["brands"] if b["id"] == "SL" and b["price"] is not None]
        if light_prices:
            offer["_sort_price"] = min(light_prices)
            priced.append(offer)
    priced.sort(key=lambda o: o["_sort_price"])
    return priced[:top_n]


def format_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if m else f"{h}h"


def display_flight(rank: int, offer: dict) -> None:
    stops = "direct" if offer["stops"] == 0 else f"{offer['stops']} stop(s)"
    dep = offer["departure"][:16].replace("T", " ") if offer["departure"] else "?"
    arr = offer["arrival"][:16].replace("T", " ") if offer["arrival"] else "?"
    duration = format_duration(offer["duration_min"]) if offer["duration_min"] else "?"

    print(f"\n{'=' * 60}")
    if rank == 1:
        print(f"  CHEAPEST FLIGHT")
    else:
        print(f"  #{rank}")
    print(f"{'=' * 60}")
    print(f"  Flight:    {offer['flight_code']}")
    print(f"  Route:     {offer['origin']} -> {offer['destination']}")
    print(f"  Departure: {dep}")
    print(f"  Arrival:   {arr}")
    print(f"  Duration:  {duration} ({stops})")
    print(f"  {'─' * 40}")
    print(f"  {'Fare Class':<20} {'Price':>15}")
    print(f"  {'─' * 40}")
    for brand in offer["brands"]:
        if brand["price"] is not None and brand["name"] is not None:
            print(f"  {brand['name']:<20} {brand['currency']} {brand['price']:>10,.2f}")
    print(f"  {'─' * 40}")


def main():
    parser = argparse.ArgumentParser(description="Find cheapest LATAM flights")
    parser.add_argument("origin", help="Origin IATA code (e.g. FOR)")
    parser.add_argument("destination", help="Destination IATA code (e.g. GRU)")
    parser.add_argument("outbound", help="Outbound date (YYYY-MM-DD)")
    parser.add_argument("inbound", help="Return date (YYYY-MM-DD)")
    parser.add_argument("-n", "--top", type=int, default=5, help="Number of cheapest flights to show (default: 5)")
    args = parser.parse_args()

    print(f"\nSearching LATAM: {args.origin} -> {args.destination}")
    print(f"Outbound: {args.outbound}  |  Return: {args.inbound}\n")

    data = search_latam(args.origin, args.destination, args.outbound, args.inbound)
    if not data:
        print("Failed to fetch flight data.")
        sys.exit(1)

    offers = parse_offers(data)
    if not offers:
        print("No flights found.")
        sys.exit(1)

    cheapest = find_cheapest_flights(offers, top_n=args.top)
    if not cheapest:
        print("No flights with pricing data found.")
        sys.exit(1)

    print(f"\nFound {len(offers)} flights total. Top {len(cheapest)} cheapest:\n")

    for i, offer in enumerate(cheapest, 1):
        display_flight(i, offer)

    print()


if __name__ == "__main__":
    main()
