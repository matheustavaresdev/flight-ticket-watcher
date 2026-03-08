def print_results(results: list, header: str = "") -> None:
    """Print flight results in a readable tabular format."""
    if header:
        print(f"\n{header}")
        print("=" * len(header))
    if not results:
        print("No flights found.")
        return
    # Print header row
    print(f"{'Price':>8}  {'Airline':<30}  {'Dep':>5}  {'Arr':>5}  {'Dur (min)':>9}  {'Stops':>5}")
    print("-" * 70)
    for r in results:
        print(f"R${r.price:>7,}  {r.airline:<30}  {r.departure_time:>5}  {r.arrival_time:>5}  {r.duration_min:>9}  {r.stops:>5}")
