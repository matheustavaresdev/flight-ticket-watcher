"""Tests for flight_watcher.queries."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from flight_watcher.models import PriceSnapshot, SearchConfig, SearchType
from flight_watcher.queries import (
    best_combinations,
    get_latest_snapshots,
    price_history,
    price_trend_summary,
    roundtrip_vs_oneway,
)


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


def _make_mock_snapshot(
    price="1000.00",
    fetched_at=None,
    origin="FOR",
    destination="MIA",
    flight_date=None,
    brand="LIGHT",
    search_type=SearchType.ONEWAY,
):
    """Mock-based snapshot for price_history/trend tests."""
    snap = MagicMock(spec=PriceSnapshot)
    snap.price = Decimal(price)
    snap.fetched_at = fetched_at or datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    snap.origin = origin
    snap.destination = destination
    snap.flight_date = flight_date or date(2026, 6, 21)
    snap.brand = brand
    snap.search_type = search_type
    return snap


def _mock_session_with_all(snapshots):
    """Session mock that returns snapshots via .execute().scalars().all()."""
    mock_session = MagicMock()
    mock_session.execute.return_value.scalars.return_value.all.return_value = snapshots
    return mock_session


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

    def test_includes_same_day_turnaround(self):
        """Same-day turnaround (trip_days == 0) should appear when max_trip_days >= 0."""
        config = _make_config(
            origin="GRU",
            destination="FOR",
            must_arrive_by=date(2024, 7, 31),
            must_stay_until=date(2024, 7, 10),
            max_trip_days=14,
        )
        same_date = date(2024, 7, 10)
        out_snap = _make_snapshot(origin="GRU", destination="FOR", flight_date=same_date, price="800.00")
        ret_snap = _make_snapshot(origin="FOR", destination="GRU", flight_date=same_date, price="700.00")

        mock_session = self._make_session(config, [out_snap, ret_snap])

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=[out_snap, ret_snap]):
            results = best_combinations(mock_session, search_config_id=1)

        assert len(results) == 1
        r = results[0]
        assert r["outbound_date"] == same_date
        assert r["return_date"] == same_date
        assert r["trip_days"] == 0
        assert r["total_price"] == Decimal("1500.00")


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

    def test_includes_same_day_pairs(self):
        """Same-day pairs (trip_days == 0) should appear when max_trip_days >= 0."""
        config = _make_config(
            origin="GRU", destination="FOR",
            must_arrive_by=date(2024, 7, 31),
            must_stay_until=date(2024, 7, 1),
            max_trip_days=30,
        )
        same_date = date(2024, 7, 10)
        rt_out = _make_snapshot(origin="GRU", destination="FOR", flight_date=same_date, price="400.00", search_type=SearchType.ROUNDTRIP)
        rt_ret = _make_snapshot(origin="FOR", destination="GRU", flight_date=same_date, price="400.00", search_type=SearchType.ROUNDTRIP)
        ow_out = _make_snapshot(origin="GRU", destination="FOR", flight_date=same_date, price="600.00", search_type=SearchType.ONEWAY)
        ow_ret = _make_snapshot(origin="FOR", destination="GRU", flight_date=same_date, price="600.00", search_type=SearchType.ONEWAY)

        mock_session = self._make_session(config)
        snaps = [rt_out, rt_ret, ow_out, ow_ret]

        with patch("flight_watcher.queries.get_latest_snapshots", return_value=snaps):
            results = roundtrip_vs_oneway(mock_session, search_config_id=1)

        assert len(results) == 1
        r = results[0]
        assert r["outbound_date"] == same_date
        assert r["return_date"] == same_date
        assert r["roundtrip_total"] == Decimal("800.00")
        assert r["oneway_total"] == Decimal("1200.00")


class TestPriceHistory:
    def test_returns_snapshots_ordered_by_fetched_at(self):
        t1 = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        snap1 = _make_mock_snapshot(fetched_at=t1)
        snap2 = _make_mock_snapshot(fetched_at=t2)
        snap3 = _make_mock_snapshot(fetched_at=t3)

        session = _mock_session_with_all([snap1, snap2, snap3])
        result = price_history(session, "FOR", "MIA", date(2026, 6, 21))

        assert result is not None
        assert result.snapshots == [snap1, snap2, snap3]
        assert result.snapshots[0].fetched_at == t1
        assert result.snapshots[2].fetched_at == t3

    def test_computes_min_max_avg(self):
        snap1 = _make_mock_snapshot(price="1000.00")
        snap2 = _make_mock_snapshot(price="1500.00")
        snap3 = _make_mock_snapshot(price="2000.00")

        session = _mock_session_with_all([snap1, snap2, snap3])
        result = price_history(session, "FOR", "MIA", date(2026, 6, 21))

        assert result is not None
        assert result.min_price == Decimal("1000.00")
        assert result.max_price == Decimal("2000.00")
        assert result.avg_price == Decimal("1500.00")

    def test_returns_none_when_no_data(self):
        session = _mock_session_with_all([])
        result = price_history(session, "FOR", "MIA", date(2026, 6, 21))
        assert result is None

    def test_filters_by_brand(self):
        snap = _make_mock_snapshot(brand="STANDARD")
        session = _mock_session_with_all([snap])
        result = price_history(session, "FOR", "MIA", date(2026, 6, 21), brand="STANDARD")
        assert result is not None
        session.execute.assert_called_once()

    def test_filters_by_search_type(self):
        snap = _make_mock_snapshot(search_type=SearchType.ROUNDTRIP)
        session = _mock_session_with_all([snap])
        result = price_history(
            session, "FOR", "MIA", date(2026, 6, 21), search_type=SearchType.ROUNDTRIP
        )
        assert result is not None
        session.execute.assert_called_once()

    def test_min_price_seen_at(self):
        t1 = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        snap1 = _make_mock_snapshot(price="2000.00", fetched_at=t1)
        snap2 = _make_mock_snapshot(price="500.00", fetched_at=t2)
        snap3 = _make_mock_snapshot(price="1000.00", fetched_at=t3)

        session = _mock_session_with_all([snap1, snap2, snap3])
        result = price_history(session, "FOR", "MIA", date(2026, 6, 21))

        assert result is not None
        assert result.min_price_seen_at == t2


class TestPriceTrendSummary:
    def _make_trend_snapshots(
        self,
        prices,
        flight_date=None,
        search_type=SearchType.ONEWAY,
    ):
        fd = flight_date or date(2026, 6, 21)
        snaps = []
        for i, price in enumerate(prices):
            snap = _make_mock_snapshot(
                price=price,
                fetched_at=datetime(2026, 3, 1, i, 0, tzinfo=timezone.utc),
                flight_date=fd,
                search_type=search_type,
            )
            snaps.append(snap)
        return snaps

    def test_rising_price(self):
        # 6 at 1000, latest at 1100.
        # rolling window (last 7, inclusive) = [1000]*6 + [1100]
        # rolling_avg ≈ 1014.28, pct_diff ≈ 8.45% > 5 → "↑"
        prices = ["1000.00"] * 6 + ["1100.00"]
        snaps = self._make_trend_snapshots(prices)
        session = _mock_session_with_all(snaps)

        result = price_trend_summary(session, search_config_id=1)

        assert len(result) == 1
        assert result[0]["direction"] == "↑"

    def test_dropping_price(self):
        # 6 at 1000, latest at 900.
        # rolling_avg ≈ 985.71, pct_diff ≈ -8.70% < -5 → "↓"
        prices = ["1000.00"] * 6 + ["900.00"]
        snaps = self._make_trend_snapshots(prices)
        session = _mock_session_with_all(snaps)

        result = price_trend_summary(session, search_config_id=1)

        assert len(result) == 1
        assert result[0]["direction"] == "↓"

    def test_stable_price(self):
        # 6 at 1000, latest at 1020.
        # rolling_avg ≈ 1002.86, pct_diff ≈ 1.71% → within ±5 → "→"
        prices = ["1000.00"] * 6 + ["1020.00"]
        snaps = self._make_trend_snapshots(prices)
        session = _mock_session_with_all(snaps)

        result = price_trend_summary(session, search_config_id=1)

        assert len(result) == 1
        assert result[0]["direction"] == "→"

    def test_empty_when_no_data(self):
        session = _mock_session_with_all([])
        result = price_trend_summary(session, search_config_id=1)
        assert result == []

    def test_rolling_avg_uses_last_7(self):
        # First 3 at 500, last 7 at 1000 (10 total).
        # Last 7 = all 1000s → rolling_avg = 1000, current = 1000.
        prices = ["500.00"] * 3 + ["1000.00"] * 7
        snaps = self._make_trend_snapshots(prices)
        session = _mock_session_with_all(snaps)

        result = price_trend_summary(session, search_config_id=1)

        assert len(result) == 1
        assert result[0]["rolling_avg_7d"] == Decimal("1000.00")
        assert result[0]["current_price"] == Decimal("1000.00")

    def test_sorted_by_flight_date(self):
        d1 = date(2026, 6, 25)
        d2 = date(2026, 6, 21)
        d3 = date(2026, 6, 23)

        snap1 = _make_mock_snapshot(
            flight_date=d1, fetched_at=datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc)
        )
        snap2 = _make_mock_snapshot(
            flight_date=d2, fetched_at=datetime(2026, 3, 1, 2, 0, tzinfo=timezone.utc)
        )
        snap3 = _make_mock_snapshot(
            flight_date=d3, fetched_at=datetime(2026, 3, 1, 3, 0, tzinfo=timezone.utc)
        )

        session = _mock_session_with_all([snap1, snap2, snap3])
        result = price_trend_summary(session, search_config_id=1)

        assert len(result) == 3
        assert result[0]["flight_date"] == d2
        assert result[1]["flight_date"] == d3
        assert result[2]["flight_date"] == d1

    def test_pct_diff_calculation(self):
        # 6 at 1000, current at 1100.
        # rolling window (last 7) = [1000,1000,1000,1000,1000,1000,1100]
        # Verify pct_diff matches the formula: (current - rolling_avg) / rolling_avg * 100
        prices = ["1000.00"] * 6 + ["1100.00"]
        snaps = self._make_trend_snapshots(prices)
        session = _mock_session_with_all(snaps)

        result = price_trend_summary(session, search_config_id=1)

        assert len(result) == 1
        all_prices = [Decimal(p) for p in prices]
        rolling_avg = sum(all_prices[-7:], Decimal("0")) / Decimal(7)
        current = Decimal("1100.00")
        expected_pct = float((current - rolling_avg) / rolling_avg * Decimal("100"))
        assert abs(result[0]["pct_diff"] - expected_pct) < 0.001
