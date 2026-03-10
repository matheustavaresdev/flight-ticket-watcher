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


def _date_range(start: date, end: date) -> list[str]:
    """Return a list of YYYY-MM-DD strings for every date from start to end inclusive."""
    result = []
    current = start
    while current <= end:
        result.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return result
