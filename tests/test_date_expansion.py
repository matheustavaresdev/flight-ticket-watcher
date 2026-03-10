"""Smoke tests for date_expansion.expand_dates().

Comprehensive tests are covered in FLI-24. These cover the core contract.
"""

import pytest
from datetime import date

from flight_watcher.date_expansion import expand_dates


def test_canonical_example():
    """Example from issue: arrive June 21, stay until June 28, max 15 days."""
    out, ret = expand_dates(date(2026, 6, 21), date(2026, 6, 28), 15)

    assert out[0] == "2026-06-13"
    assert out[-1] == "2026-06-21"
    assert len(out) == 9  # June 13–21 inclusive

    assert ret[0] == "2026-06-28"
    assert ret[-1] == "2026-07-06"
    assert len(ret) == 9  # June 28–July 6 inclusive


def test_same_day_turnaround():
    """must_arrive_by == must_stay_until (zero minimum stay)."""
    out, ret = expand_dates(date(2026, 6, 21), date(2026, 6, 21), 7)

    assert out[0] == "2026-06-14"
    assert out[-1] == "2026-06-21"
    assert ret[0] == "2026-06-21"
    assert ret[-1] == "2026-06-28"


def test_max_trip_days_equals_exact_stay():
    """max_trip_days equals the stay duration — no expansion beyond the stay endpoints."""
    # Stay: June 21 → June 28 = 7 days. max_trip_days=7.
    # earliest_departure = June 28 - 7 = June 21 (same as must_arrive_by)
    # latest_return = June 21 + 7 = June 28 (same as must_stay_until)
    out, ret = expand_dates(date(2026, 6, 21), date(2026, 6, 28), 7)

    assert out == ["2026-06-21"]
    assert ret == ["2026-06-28"]


def test_validation_negative_max_trip_days():
    """Negative max_trip_days raises ValueError."""
    with pytest.raises(ValueError, match="max_trip_days must be positive"):
        expand_dates(date(2026, 6, 21), date(2026, 6, 28), -1)


def test_validation_zero_max_trip_days():
    """Zero max_trip_days raises ValueError."""
    with pytest.raises(ValueError, match="max_trip_days must be positive"):
        expand_dates(date(2026, 6, 21), date(2026, 6, 21), 0)


def test_validation_max_trip_days_less_than_stay():
    """max_trip_days < stay duration raises ValueError."""
    # Stay June 21 → June 28 = 7 days. max_trip_days=5 < 7.
    with pytest.raises(ValueError, match="Minimum stay duration"):
        expand_dates(date(2026, 6, 21), date(2026, 6, 28), 5)


def test_validation_stay_until_before_arrive_by():
    """must_stay_until before must_arrive_by raises ValueError."""
    with pytest.raises(ValueError, match="must_stay_until.*must be on or after"):
        expand_dates(date(2026, 6, 28), date(2026, 6, 21), 15)
