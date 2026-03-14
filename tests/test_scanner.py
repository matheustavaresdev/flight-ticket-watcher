from datetime import datetime
from unittest.mock import MagicMock, patch

from flight_watcher.errors import ErrorCategory
from flight_watcher.models import FlightResult, SearchResult
from flight_watcher.scanner import (
    _map_flight_to_results,
    search_one_way,
    search_roundtrip,
)


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
    with (
        patch("flight_watcher.scanner.get_flights", return_value=mock_result),
        patch("flight_watcher.scanner.create_query"),
    ):
        result = search_one_way("FOR", "GRU", "2026-04-08")

    assert isinstance(result, SearchResult)
    assert result.ok
    assert result.data is not None
    assert len(result.data) == 1
    r = result.data[0]
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
    with (
        patch("flight_watcher.scanner.get_flights", return_value=[]),
        patch("flight_watcher.scanner.create_query"),
    ):
        result = search_one_way("FOR", "GRU", "2026-04-08")

    assert isinstance(result, SearchResult)
    assert result.ok
    assert result.data == []


def test_search_one_way_handles_exception():
    with (
        patch(
            "flight_watcher.scanner.get_flights", side_effect=Exception("network error")
        ),
        patch("flight_watcher.scanner.create_query"),
        patch("flight_watcher.scanner.random_delay", return_value=0),
    ):
        result = search_one_way("FOR", "GRU", "2026-04-08")

    assert isinstance(result, SearchResult)
    assert not result.ok
    assert result.error is not None


def test_search_one_way_circuit_breaker_open():
    with patch("flight_watcher.scanner.get_breaker") as mock_get_breaker:
        mock_breaker = MagicMock()
        mock_breaker.allow_request.return_value = False
        mock_get_breaker.return_value = mock_breaker

        result = search_one_way("FOR", "GRU", "2026-04-08")

    assert isinstance(result, SearchResult)
    assert not result.ok
    assert result.error_category == ErrorCategory.BLOCKED
    assert result.hint == "wait for breaker reset"


def test_search_roundtrip_calls_twice():
    mock_result = [_make_flight()]
    with (
        patch(
            "flight_watcher.scanner.get_flights", return_value=mock_result
        ) as mock_gf,
        patch("flight_watcher.scanner.create_query"),
        patch("flight_watcher.scanner.random_delay"),
    ):
        outbound, inbound = search_roundtrip("FOR", "GRU", "2026-04-08", "2026-04-15")

    assert mock_gf.call_count == 2
    assert isinstance(outbound, SearchResult)
    assert isinstance(inbound, SearchResult)
    assert outbound.ok
    assert inbound.ok
    assert len(outbound.data) == 1
    assert len(inbound.data) == 1
    assert outbound.data[0].origin == "FOR"
    assert outbound.data[0].destination == "GRU"
    assert inbound.data[0].origin == "GRU"
    assert inbound.data[0].destination == "FOR"


def test_map_flight_calculates_stops():
    one_segment = [_make_segment()]
    two_segments = [
        _make_segment(),
        _make_segment(dep_h=11, dep_m=0, arr_h=13, arr_m=0, duration=120),
    ]

    direct = _make_flight(segments=one_segment)
    connecting = _make_flight(segments=two_segments)

    results_direct = _map_flight_to_results([direct], "FOR", "GRU", "2026-04-08")
    results_connecting = _map_flight_to_results(
        [connecting], "FOR", "GRU", "2026-04-08"
    )

    assert results_direct[0].stops == 0
    assert results_connecting[0].stops == 1
    assert results_connecting[0].duration_min == 270
