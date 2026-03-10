"""Date expansion algorithm for flexible flight search windows."""

from datetime import date, timedelta


def expand_dates(
    must_arrive_by: date,
    must_stay_until: date,
    max_trip_days: int,
) -> tuple[list[str], list[str]]:
    """Expand outbound and return date windows given a required stay range.

    Given a date by which you must arrive and a date until which you must stay,
    this function produces all valid departure and return dates assuming a trip
    of at most ``max_trip_days`` days.

    Args:
        must_arrive_by: Latest date by which the traveler must have arrived at
            the destination. This is the upper bound for outbound_dates.
        must_stay_until: Earliest acceptable return departure date (you must
            stay until at least this date).
        max_trip_days: Maximum total trip duration in days (must be positive
            and >= the minimum stay implied by the inputs).

    Returns:
        A 2-tuple ``(outbound_dates, return_dates)`` where each element is a
        list of YYYY-MM-DD strings.

        - ``outbound_dates``: all dates from
          ``must_stay_until - max_trip_days`` up to ``must_arrive_by``.
        - ``return_dates``: all dates from ``must_stay_until`` up to
          ``must_arrive_by + max_trip_days``.

    Raises:
        ValueError: If ``max_trip_days`` is not positive, if
            ``must_stay_until`` is before ``must_arrive_by``, or if the
            minimum stay duration exceeds ``max_trip_days``.

    Example:
        >>> from datetime import date
        >>> out, ret = expand_dates(date(2026, 6, 21), date(2026, 6, 28), 15)
        >>> out[0], out[-1]
        ('2026-06-13', '2026-06-21')
        >>> ret[0], ret[-1]
        ('2026-06-28', '2026-07-06')
    """
    if max_trip_days <= 0:
        raise ValueError(f"max_trip_days must be positive, got {max_trip_days}")

    if must_stay_until < must_arrive_by:
        raise ValueError(
            f"must_stay_until ({must_stay_until}) must be on or after "
            f"must_arrive_by ({must_arrive_by})"
        )

    min_stay = (must_stay_until - must_arrive_by).days
    if min_stay > max_trip_days:
        raise ValueError(
            f"Minimum stay duration ({min_stay} days) exceeds "
            f"max_trip_days ({max_trip_days})"
        )

    earliest_departure = must_stay_until - timedelta(days=max_trip_days)
    latest_return = must_arrive_by + timedelta(days=max_trip_days)

    outbound_dates = _date_range(earliest_departure, must_arrive_by)
    return_dates = _date_range(must_stay_until, latest_return)

    return outbound_dates, return_dates


def generate_pairs(
    outbound_dates: list[str],
    return_dates: list[str],
    max_trip_days: int,
) -> list[tuple[str, str]]:
    """Generate all valid (outbound, return) date pairs within the trip duration constraint.

    Args:
        outbound_dates: List of candidate outbound dates as YYYY-MM-DD strings.
        return_dates: List of candidate return dates as YYYY-MM-DD strings.
        max_trip_days: Maximum trip duration in days (must be positive).

    Returns:
        Sorted list of (outbound_date, return_date) tuples as YYYY-MM-DD strings.
        A pair is included when ``return_date >= outbound_date`` and
        ``(return_date - outbound_date).days <= max_trip_days``.

    Raises:
        ValueError: If ``outbound_dates`` or ``return_dates`` is empty, or if
            ``max_trip_days`` is not positive.
    """
    if max_trip_days <= 0:
        raise ValueError(f"max_trip_days must be positive, got {max_trip_days}")
    if not outbound_dates:
        raise ValueError("outbound_dates must not be empty")
    if not return_dates:
        raise ValueError("return_dates must not be empty")

    pairs = []
    for out_str in outbound_dates:
        out = date.fromisoformat(out_str)
        for ret_str in return_dates:
            ret = date.fromisoformat(ret_str)
            if ret >= out and (ret - out).days <= max_trip_days:
                pairs.append((out_str, ret_str))

    pairs.sort()
    return pairs


def _date_range(start: date, end: date) -> list[str]:
    """Return a list of YYYY-MM-DD strings for every date from start to end inclusive."""
    result = []
    current = start
    while current <= end:
        result.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return result
