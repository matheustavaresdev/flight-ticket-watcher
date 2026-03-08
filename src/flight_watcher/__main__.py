import logging
from datetime import date, timedelta
from flight_watcher.scanner import search_roundtrip
from flight_watcher.display import print_results

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

def main():
    departure_date = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    return_date = (date.today() + timedelta(days=37)).strftime("%Y-%m-%d")

    print(f"Searching FOR → GRU on {departure_date} and GRU → FOR on {return_date}")

    outbound, inbound = search_roundtrip(
        origin="FOR",
        destination="GRU",
        departure_date=departure_date,
        return_date=return_date,
    )

    print_results(outbound, header=f"FOR → GRU ({departure_date})")
    print_results(inbound, header=f"GRU → FOR ({return_date})")

if __name__ == "__main__":
    main()
