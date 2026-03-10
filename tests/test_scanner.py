from datetime import datetime
from unittest.mock import MagicMock, patch

from flight_watcher.models import FlightResult
from flight_watcher.scanner import _map_flight_to_results, search_one_way, search_roundtrip


def _make_segment(dep_h=8, dep_m=0, arr_h=10, arr_m=30, duration=150):
    seg = MagicMock()
    seg.departure.time = (dep_h, dep_m)
    seg.arrival.time = (arr_h, arr_m)
    seg.duration = duration
    return seg


def _make_flight(price=500, airlines=None, segments=None):
    if airlines is None:
        airlines = ["LATAM"]
    if segments is None:
        segments = [_make_segment()]
    f = MagicMock()
    f.price = price
    f.airlines = airlines
    f.flights = segments
    return f


def test_search_one_way_returns_flight_results():
    mock_result = [_make_flight(price=800, airlines=["GOL"])]
    with patch("flight_watcher.scanner.get_flights", return_value=mock_result), \
         patch("flight_watcher.scanner.create_query"):
        results = search_one_way("FOR", "GRU", "2026-04-08")

    assert len(results) == 1
    r = results[0]
    assert isinstance(r, FlightResult)
    assert r.origin == "FOR"
    assert r.destination == "GRU"
    assert r.date == "2026-04-08"
    assert r.price == 800
    assert r.airline == "GOL"
    assert r.stops == 0
    assert r.departure_time == "08:00"
    assert r.arrival_time == "10:30"
    assert r.duration_min == 150
    assert isinstance(r.fetched_at, datetime)


def test_search_one_way_empty_results():
    with patch("flight_watcher.scanner.get_flights", return_value=[]), \
         patch("flight_watcher.scanner.create_query"):
        results = search_one_way("FOR", "GRU", "2026-04-08")

    assert results == []


def test_search_one_way_handles_exception():
    with patch("flight_watcher.scanner.get_flights", side_effect=Exception("network error")), \
         patch("flight_watcher.scanner.create_query"), \
         patch("flight_watcher.scanner.time.sleep"):
        results = search_one_way("FOR", "GRU", "2026-04-08")

    assert results == []


def test_search_roundtrip_calls_twice():
    mock_result = [_make_flight()]
    with patch("flight_watcher.scanner.get_flights", return_value=mock_result) as mock_gf, \
         patch("flight_watcher.scanner.create_query"), \
         patch("flight_watcher.scanner.time.sleep"), \
         patch("flight_watcher.scanner.random_delay"):
        outbound, inbound = search_roundtrip("FOR", "GRU", "2026-04-08", "2026-04-15")

    assert mock_gf.call_count == 2
    assert len(outbound) == 1
    assert len(inbound) == 1
    assert outbound[0].origin == "FOR"
    assert outbound[0].destination == "GRU"
    assert inbound[0].origin == "GRU"
    assert inbound[0].destination == "FOR"


def test_map_flight_calculates_stops():
    one_segment = [_make_segment()]
    two_segments = [_make_segment(), _make_segment(dep_h=11, dep_m=0, arr_h=13, arr_m=0, duration=120)]

    direct = _make_flight(segments=one_segment)
    connecting = _make_flight(segments=two_segments)

    results_direct = _map_flight_to_results([direct], "FOR", "GRU", "2026-04-08")
    results_connecting = _map_flight_to_results([connecting], "FOR", "GRU", "2026-04-08")

    assert results_direct[0].stops == 0
    assert results_connecting[0].stops == 1
    assert results_connecting[0].duration_min == 270
