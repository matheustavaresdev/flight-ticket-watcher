"""Find the cheapest LATAM flight for a given route and dates."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.flight_watcher.latam_scraper import parse_offers, search_latam, search_latam_roundtrip


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


def display_leg(label: str, cheapest: list[dict]) -> None:
    """Print a section header and all flights for a leg."""
    print(f"\n{'#' * 60}")
    print(f"  {label}")
    print(f"{'#' * 60}")
    for i, offer in enumerate(cheapest, 1):
        display_flight(i, offer)


def main():
    parser = argparse.ArgumentParser(description="Find cheapest LATAM flights")
    parser.add_argument("origin", help="Origin IATA code (e.g. FOR)")
    parser.add_argument("destination", help="Destination IATA code (e.g. GRU)")
    parser.add_argument("outbound", help="Outbound date (YYYY-MM-DD)")
    parser.add_argument("inbound", nargs="?", default=None, help="Return date (YYYY-MM-DD), omit for one-way")
    parser.add_argument("-n", "--top", type=int, default=5, help="Number of cheapest flights to show (default: 5)")
    args = parser.parse_args()

    is_roundtrip = args.inbound is not None

    print(f"\nSearching LATAM: {args.origin} -> {args.destination}")
    if is_roundtrip:
        print(f"Outbound: {args.outbound}  |  Return: {args.inbound}\n")
    else:
        print(f"Outbound: {args.outbound}  (one-way)\n")

    if is_roundtrip:
        outbound_data, return_data = search_latam_roundtrip(
            args.origin, args.destination, args.outbound, args.inbound
        )
    else:
        outbound_data = search_latam(args.origin, args.destination, args.outbound, args.outbound)
        return_data = None

    if not outbound_data:
        print("Failed to fetch outbound flight data.")
        sys.exit(1)

    outbound_offers = parse_offers(outbound_data)
    if not outbound_offers:
        print("No outbound flights found.")
        sys.exit(1)

    cheapest_outbound = find_cheapest_flights(outbound_offers, top_n=args.top)
    if not cheapest_outbound:
        print("No outbound flights with pricing data found.")
        sys.exit(1)

    print(f"\nFound {len(outbound_offers)} outbound flights total.")
    display_leg(f"OUTBOUND: {args.origin} \u2192 {args.destination} ({args.outbound})", cheapest_outbound)

    if is_roundtrip:
        if not return_data:
            print("\n[WARNING] Return flight data not captured. Showing outbound only.")
        else:
            return_offers = parse_offers(return_data)
            if not return_offers:
                print(f"\n[WARNING] No return flights found in captured data.")
            else:
                cheapest_return = find_cheapest_flights(return_offers, top_n=args.top)
                print(f"\nFound {len(return_offers)} return flights total.")

                if not cheapest_return:
                    print("No return flights with pricing data found.")
                else:
                    display_leg(f"RETURN: {args.destination} \u2192 {args.origin} ({args.inbound})", cheapest_return)

                    # Round-trip summary
                    best_out_price = cheapest_outbound[0].get("_sort_price")
                    best_ret_price = cheapest_return[0].get("_sort_price")
                    currency = next(
                        (b["currency"] for b in cheapest_outbound[0]["brands"] if b["id"] == "SL" and b["currency"]),
                        "",
                    )
                    if best_out_price is not None and best_ret_price is not None:
                        total = best_out_price + best_ret_price
                        print(f"\n{'=' * 60}")
                        print(f"  ROUND-TRIP SUMMARY")
                        print(f"{'=' * 60}")
                        print(f"  Cheapest outbound (LIGHT): {currency} {best_out_price:>10,.2f}")
                        print(f"  Cheapest return   (LIGHT): {currency} {best_ret_price:>10,.2f}")
                        print(f"  {'─' * 40}")
                        print(f"  TOTAL ROUND-TRIP:          {currency} {total:>10,.2f}")
                        print(f"{'=' * 60}")

    print()


if __name__ == "__main__":
    main()
