"""Tests for flight_watcher.queries."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from flight_watcher.models import PriceSnapshot, SearchConfig, SearchType, ScanStatus
from flight_watcher.queries import best_combinations, get_latest_snapshots, roundtrip_vs_oneway


def _make_config(
    origin="GRU",
    destination="FOR",
    must_arrive_by=date(2024, 7, 31),
    must_stay_until=date(2024, 7, 15),
    max_trip_days=14,
) -> SearchConfig:
    cfg = SearchConfig()
    cfg.id = 1
    cfg.origin = origin
    cfg.destination = destination
    cfg.must_arrive_by = must_arrive_by
    cfg.must_stay_until = must_stay_until
    cfg.max_trip_days = max_trip_days
    return cfg


def _make_snapshot(
    origin="GRU",
    destination="FOR",
    flight_date=date(2024, 7, 10),
    price="500.00",
    currency="BRL",
    brand="LIGHT",
    search_type=SearchType.ONEWAY,
    fetched_at=None,
    scan_run_id=1,
) -> PriceSnapshot:
    snap = PriceSnapshot()
    snap.scan_run_id = scan_run_id
    snap.origin = origin
    snap.destination = destination
    snap.flight_date = flight_date
    snap.flight_code = "LA3456"
    snap.departure_time = datetime(2024, 7, 10, 8, 0, tzinfo=timezone.utc)
    snap.arrival_time = datetime(2024, 7, 10, 11, 0, tzinfo=timezone.utc)
    snap.duration_min = 180
    snap.stops = 0
    snap.brand = brand
    snap.price = Decimal(price)
    snap.currency = currency
    snap.search_type = search_type
    snap.fetched_at = fetched_at or datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc)
    return snap


class TestGetLatestSnapshots:
    def test_returns_scalars_from_session(self):
        """get_latest_snapshots should execute a query and return scalar results."""
        snap = _make_snapshot()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value = [snap]

        result = get_latest_snapshots(mock_session, search_config_id=1, brand="LIGHT")

        assert result == [snap]
        mock_session.execute.assert_called_once()

    def test_returns_empty_when_no_snapshots(self):
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value = []

        result = get_latest_snapshots(mock_session, search_config_id=1)

        assert result == []

    def test_filters_by_search_type_when_provided(self):
        """Query is built without error when search_type is specified."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value = []

        result = get_latest_snapshots(
            mock_session, search_config_id=1, search_type=SearchType.ONEWAY
        )

        assert result == []
        mock_session.execute.assert_called_once()


class TestBestCombinations:
    def _make_session(self, config, snapshots):
        mock_session = MagicMock()
        mock_session.get.return_value = config
        return mock_session

    def test_returns_empty_when_config_not_found(self):
        mock_session = MagicMock()
        mock_session.get.return_value = None

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[]):
            result = best_combinations(mock_session, search_config_id=999)

        assert result == []

    def test_basic_cross_join(self):
        """Returns correct combination when single outbound and return date available."""
        config = _make_config(
            origin="GRU",
            destination="FOR",
            must_arrive_by=date(2024, 7, 31),
            must_stay_until=date(2024, 7, 15),
            max_trip_days=14,
        )
        out_snap = _make_snapshot(
            origin="GRU", destination="FOR",
            flight_date=date(2024, 7, 10), price="800.00",
        )
        ret_snap = _make_snapshot(
            origin="FOR", destination="GRU",
            flight_date=date(2024, 7, 20), price="700.00",
        )

        mock_session = self._make_session(config, [out_snap, ret_snap])

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[out_snap, ret_snap]):
            results = best_combinations(mock_session, search_config_id=1)

        assert len(results) == 1
        r = results[0]
        assert r["outbound_date"] == date(2024, 7, 10)
        assert r["return_date"] == date(2024, 7, 20)
        assert r["trip_days"] == 10
        assert r["total_price"] == Decimal("1500.00")

    def test_filters_trips_exceeding_max_trip_days(self):
        """Pairs where trip_days > max_trip_days are excluded."""
        config = _make_config(max_trip_days=7)
        out_snap = _make_snapshot(
            origin="GRU", destination="FOR",
            flight_date=date(2024, 7, 10), price="800.00",
        )
        ret_snap = _make_snapshot(
            origin="FOR", destination="GRU",
            flight_date=date(2024, 7, 20), price="700.00",
        )  # 10 days > max_trip_days=7

        mock_session = self._make_session(config, [out_snap, ret_snap])

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[out_snap, ret_snap]):
            results = best_combinations(mock_session, search_config_id=1)

        assert results == []

    def test_groups_by_trip_days_keeps_cheapest(self):
        """For same trip_days, only the cheapest combination is kept."""
        config = _make_config(max_trip_days=14)
        # Two outbound dates: Jul 10 and Jul 11 — both with return Jul 20 → 10 and 9 days
        # Jul 10 → Jul 20 = 10 days, total = 800+700 = 1500
        # Jul 11 → Jul 20 = 9 days (different trip_days, no conflict)
        # Add another Jul 10 → Jul 20 pair via different outbound price to test cheapest kept
        out_cheap = _make_snapshot(
            origin="GRU", destination="FOR",
            flight_date=date(2024, 7, 10), price="600.00",
        )
        out_expensive = _make_snapshot(
            origin="GRU", destination="FOR",
            flight_date=date(2024, 7, 10), price="900.00",
            fetched_at=datetime(2024, 7, 2, 12, 0, tzinfo=timezone.utc),
        )
        ret_snap = _make_snapshot(
            origin="FOR", destination="GRU",
            flight_date=date(2024, 7, 20), price="700.00",
        )

        mock_session = self._make_session(config, [out_cheap, out_expensive, ret_snap])

        with patch(
            "flight_watcher.queries.get_latest_snapshots",
            return_value=[out_cheap, out_expensive, ret_snap],
        ):
            results = best_combinations(mock_session, search_config_id=1)

        # Both have trip_days=10, only cheapest (600+700=1300) should survive
        assert len(results) == 1
        assert results[0]["total_price"] == Decimal("1300.00")

    def test_sorted_by_total_price(self):
        """Results are sorted ascending by total_price."""
        config = _make_config(max_trip_days=30)
        out1 = _make_snapshot(origin="GRU", destination="FOR", flight_date=date(2024, 7, 5), price="1000.00")
        out2 = _make_snapshot(origin="GRU", destination="FOR", flight_date=date(2024, 7, 10), price="500.00")
        ret = _make_snapshot(origin="FOR", destination="GRU", flight_date=date(2024, 7, 20), price="500.00")

        mock_session = self._make_session(config, [out1, out2, ret])

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[out1, out2, ret]):
            results = best_combinations(mock_session, search_config_id=1)

        totals = [r["total_price"] for r in results]
        assert totals == sorted(totals)


class TestRoundtripVsOneway:
    def _make_session(self, config):
        mock_session = MagicMock()
        mock_session.get.return_value = config
        return mock_session

    def test_returns_empty_when_config_not_found(self):
        mock_session = MagicMock()
        mock_session.get.return_value = None

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[]):
            result = roundtrip_vs_oneway(mock_session, search_config_id=999)

        assert result == []

    def test_returns_empty_when_no_data(self):
        config = _make_config()
        mock_session = self._make_session(config)

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[]):
            result = roundtrip_vs_oneway(mock_session, search_config_id=1)

        assert result == []

    def test_comparison_roundtrip_cheaper(self):
        """When roundtrip total < oneway total, recommendation is 'roundtrip'."""
        config = _make_config(
            origin="GRU", destination="FOR",
            must_arrive_by=date(2024, 7, 31),
            must_stay_until=date(2024, 7, 1),
            max_trip_days=30,
        )
        rt_out = _make_snapshot(
            origin="GRU", destination="FOR",
            flight_date=date(2024, 7, 10), price="400.00",
            search_type=SearchType.ROUNDTRIP,
        )
        rt_ret = _make_snapshot(
            origin="FOR", destination="GRU",
            flight_date=date(2024, 7, 20), price="400.00",
            search_type=SearchType.ROUNDTRIP,
        )
        ow_out = _make_snapshot(
            origin="GRU", destination="FOR",
            flight_date=date(2024, 7, 10), price="600.00",
            search_type=SearchType.ONEWAY,
        )
        ow_ret = _make_snapshot(
            origin="FOR", destination="GRU",
            flight_date=date(2024, 7, 20), price="600.00",
            search_type=SearchType.ONEWAY,
        )

        mock_session = self._make_session(config)
        snaps = [rt_out, rt_ret, ow_out, ow_ret]

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=snaps):
            results = roundtrip_vs_oneway(mock_session, search_config_id=1)

        assert len(results) == 1
        r = results[0]
        assert r["roundtrip_total"] == Decimal("800.00")
        assert r["oneway_total"] == Decimal("1200.00")
        assert r["recommendation"] == "roundtrip"
        assert r["significant"] is True  # savings > 5%

    def test_comparison_oneway_cheaper(self):
        """When oneway total < roundtrip total, recommendation is '2x one-way'."""
        config = _make_config(
            origin="GRU", destination="FOR",
            must_arrive_by=date(2024, 7, 31),
            must_stay_until=date(2024, 7, 1),
            max_trip_days=30,
        )
        rt_out = _make_snapshot(
            origin="GRU", destination="FOR",
            flight_date=date(2024, 7, 10), price="700.00",
            search_type=SearchType.ROUNDTRIP,
        )
        rt_ret = _make_snapshot(
            origin="FOR", destination="GRU",
            flight_date=date(2024, 7, 20), price="700.00",
            search_type=SearchType.ROUNDTRIP,
        )
        ow_out = _make_snapshot(
            origin="GRU", destination="FOR",
            flight_date=date(2024, 7, 10), price="500.00",
            search_type=SearchType.ONEWAY,
        )
        ow_ret = _make_snapshot(
            origin="FOR", destination="GRU",
            flight_date=date(2024, 7, 20), price="500.00",
            search_type=SearchType.ONEWAY,
        )

        mock_session = self._make_session(config)
        snaps = [rt_out, rt_ret, ow_out, ow_ret]

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=snaps):
            results = roundtrip_vs_oneway(mock_session, search_config_id=1)

        assert len(results) == 1
        r = results[0]
        assert r["recommendation"] == "2x one-way"

    def test_savings_pct_calculation(self):
        """savings_pct is correctly calculated."""
        config = _make_config(
            origin="GRU", destination="FOR",
            must_arrive_by=date(2024, 7, 31),
            must_stay_until=date(2024, 7, 1),
            max_trip_days=30,
        )
        # RT: 800, OW: 1000 → savings = 200/1000 = 20%
        rt_out = _make_snapshot(origin="GRU", destination="FOR", flight_date=date(2024, 7, 10), price="400.00", search_type=SearchType.ROUNDTRIP)
        rt_ret = _make_snapshot(origin="FOR", destination="GRU", flight_date=date(2024, 7, 20), price="400.00", search_type=SearchType.ROUNDTRIP)
        ow_out = _make_snapshot(origin="GRU", destination="FOR", flight_date=date(2024, 7, 10), price="500.00", search_type=SearchType.ONEWAY)
        ow_ret = _make_snapshot(origin="FOR", destination="GRU", flight_date=date(2024, 7, 20), price="500.00", search_type=SearchType.ONEWAY)

        mock_session = self._make_session(config)

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[rt_out, rt_ret, ow_out, ow_ret]):
            results = roundtrip_vs_oneway(mock_session, search_config_id=1)

        assert len(results) == 1
        assert abs(results[0]["savings_pct"] - 20.0) < 0.01

    def test_significant_flag_threshold(self):
        """significant is True when savings_pct > 5%, False otherwise."""
        config = _make_config(
            origin="GRU", destination="FOR",
            must_arrive_by=date(2024, 7, 31),
            must_stay_until=date(2024, 7, 1),
            max_trip_days=30,
        )
        # RT: 990, OW: 1000 → savings = 10/1000 = 1% → NOT significant
        rt_out = _make_snapshot(origin="GRU", destination="FOR", flight_date=date(2024, 7, 10), price="495.00", search_type=SearchType.ROUNDTRIP)
        rt_ret = _make_snapshot(origin="FOR", destination="GRU", flight_date=date(2024, 7, 20), price="495.00", search_type=SearchType.ROUNDTRIP)
        ow_out = _make_snapshot(origin="GRU", destination="FOR", flight_date=date(2024, 7, 10), price="500.00", search_type=SearchType.ONEWAY)
        ow_ret = _make_snapshot(origin="FOR", destination="GRU", flight_date=date(2024, 7, 20), price="500.00", search_type=SearchType.ONEWAY)

        mock_session = self._make_session(config)

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[rt_out, rt_ret, ow_out, ow_ret]):
            results = roundtrip_vs_oneway(mock_session, search_config_id=1)

        assert len(results) == 1
        assert results[0]["significant"] is False

    def test_excludes_pairs_exceeding_max_trip_days(self):
        """Date pairs with trip_days > max_trip_days are excluded."""
        config = _make_config(
            origin="GRU", destination="FOR",
            must_arrive_by=date(2024, 7, 31),
            must_stay_until=date(2024, 7, 1),
            max_trip_days=7,
        )
        # Jul 10 → Jul 20 = 10 days > 7
        rt_out = _make_snapshot(origin="GRU", destination="FOR", flight_date=date(2024, 7, 10), price="400.00", search_type=SearchType.ROUNDTRIP)
        rt_ret = _make_snapshot(origin="FOR", destination="GRU", flight_date=date(2024, 7, 20), price="400.00", search_type=SearchType.ROUNDTRIP)
        ow_out = _make_snapshot(origin="GRU", destination="FOR", flight_date=date(2024, 7, 10), price="500.00", search_type=SearchType.ONEWAY)
        ow_ret = _make_snapshot(origin="FOR", destination="GRU", flight_date=date(2024, 7, 20), price="500.00", search_type=SearchType.ONEWAY)

        mock_session = self._make_session(config)

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[rt_out, rt_ret, ow_out, ow_ret]):
            results = roundtrip_vs_oneway(mock_session, search_config_id=1)

        assert results == []
