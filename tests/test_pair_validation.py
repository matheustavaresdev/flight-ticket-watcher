"""Tests for generate_pairs() in date_expansion."""

import pytest
from datetime import date

from flight_watcher.date_expansion import expand_dates, generate_pairs


def test_canonical_45_pairs():
    outbound, returns = expand_dates(date(2026, 6, 21), date(2026, 6, 28), 15)
    pairs = generate_pairs(outbound, returns, 15)
    assert len(pairs) == 45
    assert pairs[0] == ("2026-06-13", "2026-06-28")
    assert pairs[-1] == ("2026-06-21", "2026-07-06")


def test_tight_constraint_single_pair():
    # outbound June 20, return June 28: only delta=8 qualifies with max_trip_days=8
    pairs = generate_pairs(["2026-06-20"], ["2026-06-28"], 8)
    assert pairs == [("2026-06-20", "2026-06-28")]


def test_same_day_turnaround():
    pairs = generate_pairs(["2026-06-20"], ["2026-06-20"], 5)
    assert pairs == [("2026-06-20", "2026-06-20")]


def test_return_before_outbound_excluded():
    # return before outbound should never appear
    pairs = generate_pairs(["2026-06-20"], ["2026-06-15"], 15)
    assert pairs == []


def test_validation_empty_outbound():
    with pytest.raises(ValueError, match="outbound_dates"):
        generate_pairs([], ["2026-06-28"], 10)


def test_validation_empty_return():
    with pytest.raises(ValueError, match="return_dates"):
        generate_pairs(["2026-06-20"], [], 10)


def test_validation_non_positive_max_trip_days():
    with pytest.raises(ValueError, match="max_trip_days"):
        generate_pairs(["2026-06-20"], ["2026-06-28"], 0)
    with pytest.raises(ValueError, match="max_trip_days"):
        generate_pairs(["2026-06-20"], ["2026-06-28"], -5)


def test_pairs_sorted():
    outbound = ["2026-06-21", "2026-06-20"]
    returns = ["2026-06-28", "2026-06-25"]
    pairs = generate_pairs(outbound, returns, 15)
    assert pairs == sorted(pairs)


def test_month_boundary_pairs():
    """Pairs from month-spanning expand_dates are all valid."""
    # outbound May 23-28, return June 2-7, max_trip_days=10
    outbound, returns = expand_dates(date(2026, 5, 28), date(2026, 6, 2), 10)
    pairs = generate_pairs(outbound, returns, 10)

    # All pairs must have return >= outbound and delta <= 10
    for out_str, ret_str in pairs:
        out_d = date.fromisoformat(out_str)
        ret_d = date.fromisoformat(ret_str)
        assert ret_d >= out_d
        assert (ret_d - out_d).days <= 10

    # outbound May 23: only June 2 (delta=10) qualifies → 1 pair
    # outbound May 24: June 2 (9), June 3 (10) → 2 pairs
    # ... outbound May 28: June 2-7 all qualify (5-10 days) → 6 pairs
    # Total = 1+2+3+4+5+6 = 21
    assert len(pairs) == 21


def test_large_window_pair_count():
    """30+ day window pair count follows the triangular formula."""
    # outbound May 1-June 1 (32 dates), return June 5-July 6 (32 dates), max=35
    outbound, returns = expand_dates(date(2026, 6, 1), date(2026, 6, 5), 35)
    pairs = generate_pairs(outbound, returns, 35)

    # outbound May 1: only June 5 (delta=35) → 1 pair
    # outbound May 2: June 5 (34), June 6 (35) → 2 pairs
    # ...
    # outbound June 1: June 5-July 6 all qualify (4-35 days) → 32 pairs
    # Total = 1+2+...+32 = 32*33/2 = 528
    assert len(pairs) == 528


def test_max_trip_equals_min_stay_single_pair():
    """expand_dates with max_trip_days==stay_duration feeds into exactly 1 pair."""
    outbound, returns = expand_dates(date(2026, 6, 21), date(2026, 6, 28), 7)
    pairs = generate_pairs(outbound, returns, 7)

    assert pairs == [("2026-06-21", "2026-06-28")]


def test_multiple_outbound_single_return():
    """3 outbound dates, 1 return date → all 3 pairs included when within constraint."""
    outbound = ["2026-06-19", "2026-06-20", "2026-06-21"]
    returns = ["2026-06-28"]
    pairs = generate_pairs(outbound, returns, 15)

    assert len(pairs) == 3
    assert ("2026-06-19", "2026-06-28") in pairs
    assert ("2026-06-20", "2026-06-28") in pairs
    assert ("2026-06-21", "2026-06-28") in pairs


def test_single_outbound_multiple_return():
    """1 outbound date, 3 return dates → all 3 pairs included when within constraint."""
    outbound = ["2026-06-20"]
    returns = ["2026-06-25", "2026-06-28", "2026-07-01"]
    pairs = generate_pairs(outbound, returns, 15)

    assert len(pairs) == 3
    assert ("2026-06-20", "2026-06-25") in pairs
    assert ("2026-06-20", "2026-06-28") in pairs
    assert ("2026-06-20", "2026-07-01") in pairs
