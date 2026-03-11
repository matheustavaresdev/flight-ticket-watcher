"""Find cheapest (outbound, return) flight combinations from stored price data."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flight_watcher.db import get_session
from flight_watcher.queries import best_combinations


def format_date(d) -> str:
    return d.strftime("%b %d")


def main():
    parser = argparse.ArgumentParser(
        description="Find cheapest outbound+return combinations for a search config"
    )
    parser.add_argument("search_config_id", type=int, help="SearchConfig ID to query")
    parser.add_argument("--brand", default="LIGHT", help="Fare brand (default: LIGHT)")
    parser.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
    args = parser.parse_args()

    with get_session() as session:
        results = best_combinations(session, args.search_config_id, brand=args.brand, limit=args.limit)

    if not results:
        print(f"No combinations found for search_config_id={args.search_config_id}.")
        sys.exit(0)

    print(f"\nBest combinations for config {args.search_config_id} [{args.brand}]:")
    print("=" * 60)
    for r in results:
        out_str = format_date(r["outbound_date"])
        ret_str = format_date(r["return_date"])
        currency = r["currency"]
        total = r["total_price"]
        print(f"  Stay {r['trip_days']} days ({out_str} \u2192 {ret_str}): {currency} {total:,.2f}")
    print()


if __name__ == "__main__":
    main()
