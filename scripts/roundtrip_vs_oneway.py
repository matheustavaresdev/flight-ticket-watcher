"""Compare roundtrip vs 2x one-way pricing from stored price data."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flight_watcher.db import get_session
from flight_watcher.queries import roundtrip_vs_oneway


def format_date(d) -> str:
    return d.strftime("%b %d")


def main():
    parser = argparse.ArgumentParser(
        description="Compare roundtrip vs 2x one-way pricing for a search config"
    )
    parser.add_argument("search_config_id", type=int, help="SearchConfig ID to query")
    parser.add_argument("--brand", default="LIGHT", help="Fare brand (default: LIGHT)")
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="Savings %% threshold to flag as significant (default: 5.0)",
    )
    args = parser.parse_args()

    with get_session() as session:
        results = roundtrip_vs_oneway(session, args.search_config_id, brand=args.brand)

    # Apply threshold override (default in queries.py is 5, but script may override display)
    for r in results:
        r["significant"] = r["savings_pct"] > args.threshold

    if not results:
        print(f"No comparison data found for search_config_id={args.search_config_id}.")
        sys.exit(0)

    print(f"\nRoundtrip vs One-way comparison for config {args.search_config_id} [{args.brand}]:")
    print("=" * 72)
    print(f"  {'Dates':<22} {'RT Total':>12} {'OW Total':>12} {'Savings':>8}  {'Recommendation'}")
    print(f"  {'-' * 68}")
    for r in results:
        dates = f"{format_date(r['outbound_date'])} \u2192 {format_date(r['return_date'])}"
        flag = " *" if r["significant"] else "  "
        print(
            f"  {dates:<22} {r['roundtrip_total']:>12,.2f} {r['oneway_total']:>12,.2f} "
            f"{r['savings_pct']:>7.1f}%{flag} {r['recommendation']}"
        )
    print()
    significant = [r for r in results if r["significant"]]
    if significant:
        print(f"  * Significant savings (>{args.threshold:.0f}%): {len(significant)} date pair(s)")
        print()


if __name__ == "__main__":
    main()
