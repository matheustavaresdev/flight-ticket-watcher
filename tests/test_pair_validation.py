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
