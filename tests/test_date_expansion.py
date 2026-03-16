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


def test_month_boundary_spanning():
    """Dates spanning a month boundary: arrive by May 28, stay until June 2, max 10 days."""
    # earliest_departure = June 2 - 10 = May 23
    # latest_return = May 28 + 10 = June 7
    out, ret = expand_dates(date(2026, 5, 28), date(2026, 6, 2), 10)

    assert out[0] == "2026-05-23"
    assert out[-1] == "2026-05-28"
    assert ret[0] == "2026-06-02"
    assert ret[-1] == "2026-06-07"
    # outbound in May, return in June
    assert all(d.startswith("2026-05") for d in out)
    assert all(d.startswith("2026-06") for d in ret)


def test_large_window_30_plus_days():
    """30+ day max trip: arrive by June 1, stay until June 5, max 35 days."""
    # earliest_departure = June 5 - 35 = May 1
    # latest_return = June 1 + 35 = July 6
    out, ret = expand_dates(date(2026, 6, 1), date(2026, 6, 5), 35)

    assert out[0] == "2026-05-01"
    assert out[-1] == "2026-06-01"
    assert len(out) == 32  # May 1 to June 1 inclusive

    assert ret[0] == "2026-06-05"
    assert ret[-1] == "2026-07-06"
    assert len(ret) == 32  # June 5 to July 6 inclusive


def test_single_day_max_trip_equals_one():
    """max_trip_days=1 with same-day arrive/stay: outbound and return each span 2 dates."""
    # must_arrive_by = must_stay_until = June 15
    # earliest_departure = June 15 - 1 = June 14
    # latest_return = June 15 + 1 = June 16
    out, ret = expand_dates(date(2026, 6, 15), date(2026, 6, 15), 1)

    assert out == ["2026-06-14", "2026-06-15"]
    assert ret == ["2026-06-15", "2026-06-16"]


def test_year_boundary():
    """Dates spanning year boundary: arrive by Dec 30, stay until Jan 2, max 10 days."""
    # earliest_departure = Jan 2, 2027 - 10 = Dec 23, 2026
    # latest_return = Dec 30, 2026 + 10 = Jan 9, 2027
    out, ret = expand_dates(date(2026, 12, 30), date(2027, 1, 2), 10)

    assert out[0] == "2026-12-23"
    assert out[-1] == "2026-12-30"
    assert len(out) == 8  # Dec 23–30 inclusive

    assert ret[0] == "2027-01-02"
    assert ret[-1] == "2027-01-09"
    assert len(ret) == 8  # Jan 2–9 inclusive


def test_min_trip_days_validation_zero():
    """min_trip_days=0 raises ValueError."""
    with pytest.raises(ValueError, match="min_trip_days must be >= 1"):
        expand_dates(date(2026, 6, 21), date(2026, 6, 28), 15, min_trip_days=0)


def test_min_trip_days_validation_negative():
    """Negative min_trip_days raises ValueError."""
    with pytest.raises(ValueError, match="min_trip_days must be >= 1"):
        expand_dates(date(2026, 6, 21), date(2026, 6, 28), 15, min_trip_days=-3)


def test_min_trip_days_exceeds_max():
    """min_trip_days > max_trip_days raises ValueError."""
    with pytest.raises(ValueError, match="min_trip_days.*must be <= max_trip_days"):
        expand_dates(date(2026, 6, 21), date(2026, 6, 28), 15, min_trip_days=20)


def test_min_trip_days_valid_passes_through():
    """Valid min_trip_days does not raise and returns date lists."""
    out, ret = expand_dates(date(2026, 6, 21), date(2026, 6, 28), 15, min_trip_days=7)
    assert len(out) > 0
    assert len(ret) > 0
