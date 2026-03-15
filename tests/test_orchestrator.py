import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

MODULE = "flight_watcher.orchestrator"


def _make_config(
    id=1,
    origin="GRU",
    destination="GIG",
    must_arrive_by=date(2026, 6, 21),
    must_stay_until=date(2026, 6, 28),
    max_trip_days=15,
    active=True,
):
    return {
        "id": id,
        "origin": origin,
        "destination": destination,
        "must_arrive_by": must_arrive_by,
        "must_stay_until": must_stay_until,
        "max_trip_days": max_trip_days,
    }


def _make_flight_result(
    origin="GRU",
    destination="GIG",
    date_str="2026-06-13",
    price=500,
    airline="LATAM",
    duration_min=90,
    stops=0,
    departure_time="08:00",
    arrival_time="09:30",
):
    from flight_watcher.models import FlightResult

    return FlightResult(
        origin=origin,
        destination=destination,
        date=date_str,
        price=price,
        airline=airline,
        duration_min=duration_min,
        stops=stops,
        departure_time=departure_time,
        arrival_time=arrival_time,
        fetched_at=datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc),
    )


def _make_scan_run(
    id=1, config_id=1, status=None, last_successful_date=None, started_at=None
):
    from flight_watcher.models import ScanStatus

    m = MagicMock()
    m.id = id
    m.search_config_id = config_id
    m.status = status or ScanStatus.RUNNING
    m.last_successful_date = last_successful_date
    m.started_at = started_at or datetime(2026, 3, 11, 3, 0, tzinfo=timezone.utc)
    m.error_message = None
    m.completed_at = None
    return m


class TestRunAllScans(unittest.TestCase):
    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    def test_run_all_scans_loads_active_configs(self, mock_run_scan, mock_get_session):
        """Verifies query filters by active=True and calls run_scan for each."""
        # ORM-like objects returned by the session (before extraction to dicts)
        orm1 = MagicMock()
        orm1.id = 1
        orm1.origin = "GRU"
        orm1.destination = "GIG"
        orm1.must_arrive_by = date(2026, 6, 21)
        orm1.must_stay_until = date(2026, 6, 28)
        orm1.max_trip_days = 15

        orm2 = MagicMock()
        orm2.id = 2
        orm2.origin = "GRU"
        orm2.destination = "SSA"
        orm2.must_arrive_by = date(2026, 7, 1)
        orm2.must_stay_until = date(2026, 7, 8)
        orm2.max_trip_days = 10

        mock_session = MagicMock()
        mock_session.scalars.return_value.all.return_value = [orm1, orm2]
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_all_scans

        run_all_scans()

        self.assertEqual(mock_run_scan.call_count, 2)
        # Verify dicts are passed (not ORM objects)
        first_call_arg = mock_run_scan.call_args_list[0][0][0]
        self.assertIsInstance(first_call_arg, dict)
        self.assertEqual(first_call_arg["id"], 1)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    def test_run_all_scans_continues_on_error(self, mock_run_scan, mock_get_session):
        """Verifies that an error in one config does not stop others."""
        orm1 = MagicMock()
        orm1.id = 1
        orm1.origin = "GRU"
        orm1.destination = "GIG"
        orm1.must_arrive_by = date(2026, 6, 21)
        orm1.must_stay_until = date(2026, 6, 28)
        orm1.max_trip_days = 15

        orm2 = MagicMock()
        orm2.id = 2
        orm2.origin = "GRU"
        orm2.destination = "SSA"
        orm2.must_arrive_by = date(2026, 7, 1)
        orm2.must_stay_until = date(2026, 7, 8)
        orm2.max_trip_days = 10

        mock_session = MagicMock()
        mock_session.scalars.return_value.all.return_value = [orm1, orm2]
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_run_scan.side_effect = [Exception("boom"), None]

        from flight_watcher.orchestrator import run_all_scans

        run_all_scans()  # should not raise

        self.assertEqual(mock_run_scan.call_count, 2)


class TestRunScan(unittest.TestCase):
    def _setup_session_mock(self, mock_get_session, scan_run=None, resumable=None):
        """Helper to set up a session mock."""
        mock_session = MagicMock()
        if scan_run:
            # simulate session.flush() populating the id
            def flush_side_effect():
                pass

            mock_session.flush.side_effect = flush_side_effect
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        return mock_session

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_run_scan_creates_scan_run(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """Verifies ScanRun created with status=RUNNING."""
        from flight_watcher.models import ScanRun, ScanStatus, SearchResult

        mock_search.return_value = SearchResult.success(2)
        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        config = _make_config()
        captured_status_at_add = {}
        mock_session = MagicMock()

        # Capture the status at the time add() is called, before run_scan mutates it
        def add_side_effect(obj):
            if isinstance(obj, ScanRun):
                obj.id = 1
                captured_status_at_add["status"] = obj.status

        mock_session.add.side_effect = add_side_effect
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_scan

        run_scan(config)

        self.assertIn(
            "status", captured_status_at_add, "ScanRun was not added to session"
        )
        self.assertEqual(captured_status_at_add["status"], ScanStatus.RUNNING)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_run_scan_marks_completed_on_success(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """Verifies status=COMPLETED and completed_at are set on success."""
        from flight_watcher.models import ScanRun, ScanStatus, SearchResult

        mock_search.return_value = SearchResult.success(1)
        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        config = _make_config()
        captured = {}

        mock_session = MagicMock()

        def add_side_effect(obj):
            if isinstance(obj, ScanRun):
                obj.id = 1
                captured["scan_run"] = obj

        mock_session.add.side_effect = add_side_effect
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_scan

        run_scan(config)

        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].status, ScanStatus.COMPLETED)
        self.assertIsNotNone(captured["scan_run"].completed_at)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_run_scan_marks_failed_on_error(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """Verifies status=FAILED and error_message saved on unhandled error."""
        from flight_watcher.models import ScanRun, ScanStatus

        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        mock_search.side_effect = RuntimeError("search exploded")
        config = _make_config()
        captured = {}

        mock_session = MagicMock()

        def add_side_effect(obj):
            if isinstance(obj, ScanRun):
                obj.id = 1
                captured["scan_run"] = obj

        mock_session.add.side_effect = add_side_effect
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_scan

        with self.assertRaises(RuntimeError):
            run_scan(config)

        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].status, ScanStatus.FAILED)
        self.assertEqual(captured["scan_run"].error_message, "search exploded")

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_run_scan_updates_cursor_after_each_date(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """Verifies last_successful_date is updated after each date."""
        from flight_watcher.models import ScanRun, SearchResult

        mock_search.return_value = SearchResult.success(2)
        mock_expand.return_value = (["2026-06-13", "2026-06-14"], ["2026-06-28"])
        config = _make_config()
        captured = {}

        mock_session = MagicMock()

        def add_side_effect(obj):
            if isinstance(obj, ScanRun):
                obj.id = 1
                captured["scan_run"] = obj

        mock_session.add.side_effect = add_side_effect
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_scan

        run_scan(config)

        # All unique dates: 2026-06-13, 2026-06-14, 2026-06-28
        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].last_successful_date, date(2026, 6, 28))

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_empty_search_results_continues(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """Empty results (no flights found) don't fail the run — cursor advances."""
        from flight_watcher.models import ScanRun, ScanStatus, SearchResult

        mock_search.return_value = SearchResult.success(0)
        mock_expand.return_value = (["2026-06-13", "2026-06-14"], ["2026-06-28"])
        config = _make_config()
        captured = {}

        mock_session = MagicMock()

        def add_side_effect(obj):
            if isinstance(obj, ScanRun):
                obj.id = 1
                captured["scan_run"] = obj

        mock_session.add.side_effect = add_side_effect
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_scan

        run_scan(config)

        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].status, ScanStatus.COMPLETED)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_run_scan_expands_dates_and_searches(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """Verifies search_one_way called for each date in both directions via _search_and_store_oneway."""
        from flight_watcher.models import ScanRun, SearchResult

        mock_search.return_value = SearchResult.success(1)
        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        config = _make_config(origin="GRU", destination="GIG")

        mock_session = MagicMock()

        def add_side_effect(obj):
            if isinstance(obj, ScanRun):
                obj.id = 1

        mock_session.add.side_effect = add_side_effect
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_scan

        run_scan(config)

        # unique dates: 2026-06-13, 2026-06-28 — each searched in both directions
        # 2 dates × 2 directions = 4 calls
        self.assertEqual(mock_search.call_count, 4)


class TestFindResumableRun(unittest.TestCase):
    @patch(f"{MODULE}.datetime")
    def test_find_resumable_run_returns_todays_failed_run(self, mock_dt):
        """Returns a FAILED run started today."""
        from flight_watcher.models import ScanStatus

        mock_dt.now.return_value = datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        mock_session = MagicMock()
        run = _make_scan_run(
            id=5,
            status=ScanStatus.FAILED,
            started_at=datetime(2026, 3, 11, 3, 0, tzinfo=timezone.utc),
        )
        mock_session.scalars.return_value.first.return_value = run

        from flight_watcher.orchestrator import _find_resumable_run

        result = _find_resumable_run(mock_session, config_id=1)
        self.assertIs(result, run)

    @patch(f"{MODULE}.datetime")
    def test_find_resumable_run_returns_none_if_no_prior(self, mock_dt):
        """Returns None when no run exists today."""
        mock_dt.now.return_value = datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        mock_session = MagicMock()
        mock_session.scalars.return_value.first.return_value = None

        from flight_watcher.orchestrator import _find_resumable_run

        result = _find_resumable_run(mock_session, config_id=1)
        self.assertIsNone(result)

    @patch(f"{MODULE}.datetime")
    def test_find_resumable_run_returns_none_if_from_yesterday(self, mock_dt):
        """Returns None if the only run was from yesterday."""
        from flight_watcher.models import ScanStatus

        mock_dt.now.return_value = datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        mock_session = MagicMock()
        run = _make_scan_run(
            id=5,
            status=ScanStatus.FAILED,
            started_at=datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc),
        )
        mock_session.scalars.return_value.first.return_value = run

        from flight_watcher.orchestrator import _find_resumable_run

        result = _find_resumable_run(mock_session, config_id=1)
        self.assertIsNone(result)


class TestDatesAfterCursor(unittest.TestCase):
    def test_dates_after_cursor_no_cursor(self):
        from flight_watcher.orchestrator import _dates_after_cursor

        dates = ["2026-06-13", "2026-06-14", "2026-06-28"]
        result = _dates_after_cursor(dates, None)
        self.assertEqual(result, dates)

    def test_dates_after_cursor_filters_completed(self):
        from flight_watcher.orchestrator import _dates_after_cursor

        dates = ["2026-06-13", "2026-06-14", "2026-06-15", "2026-06-28"]
        cursor = date(2026, 6, 14)
        result = _dates_after_cursor(dates, cursor)
        self.assertEqual(result, ["2026-06-15", "2026-06-28"])

    def test_dates_after_cursor_all_done(self):
        from flight_watcher.orchestrator import _dates_after_cursor

        dates = ["2026-06-13", "2026-06-14"]
        cursor = date(2026, 6, 14)
        result = _dates_after_cursor(dates, cursor)
        self.assertEqual(result, [])


class TestFlightResultToSnapshot(unittest.TestCase):
    def test_flight_result_to_snapshot_conversion(self):
        """Verifies all field mappings from FlightResult to PriceSnapshot."""
        from flight_watcher.models import SearchType
        from flight_watcher.orchestrator import _flight_result_to_snapshot

        result = _make_flight_result(
            origin="GRU",
            destination="GIG",
            date_str="2026-06-13",
            price=500,
            airline="LATAM Airlines",
            duration_min=90,
            stops=0,
            departure_time="08:00",
            arrival_time="09:30",
        )

        snapshot = _flight_result_to_snapshot(
            result, scan_run_id=42, search_type=SearchType.ONEWAY
        )

        self.assertEqual(snapshot.scan_run_id, 42)
        self.assertEqual(snapshot.origin, "GRU")
        self.assertEqual(snapshot.destination, "GIG")
        self.assertEqual(snapshot.flight_date, date(2026, 6, 13))
        self.assertEqual(snapshot.flight_code, "LATAM Airlines")
        self.assertEqual(
            snapshot.departure_time, datetime(2026, 6, 13, 8, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(
            snapshot.arrival_time, datetime(2026, 6, 13, 9, 30, tzinfo=timezone.utc)
        )
        self.assertEqual(snapshot.duration_min, 90)
        self.assertEqual(snapshot.stops, 0)
        self.assertEqual(snapshot.brand, "ECONOMY")
        self.assertEqual(snapshot.price, Decimal(500))
        self.assertEqual(snapshot.currency, "BRL")
        self.assertEqual(snapshot.search_type, SearchType.ONEWAY)

    def test_fetched_at_gets_utc_marker(self):
        """FlightResult.fetched_at without tzinfo gets UTC marker."""
        from flight_watcher.models import SearchType
        from flight_watcher.orchestrator import _flight_result_to_snapshot
        from flight_watcher.models import FlightResult

        result = FlightResult(
            origin="GRU",
            destination="GIG",
            date="2026-06-13",
            price=300,
            airline="GOL",
            duration_min=60,
            stops=0,
            departure_time="10:00",
            arrival_time="11:00",
            fetched_at=datetime(2026, 6, 13, 10, 0),  # naive datetime
        )
        snapshot = _flight_result_to_snapshot(
            result, scan_run_id=1, search_type=SearchType.ONEWAY
        )
        self.assertEqual(snapshot.fetched_at.tzinfo, timezone.utc)

    def test_overnight_flight_arrival_advances_one_day(self):
        """Overnight flights (arrive next day) get arrival_dt bumped by one day."""
        from flight_watcher.models import SearchType
        from flight_watcher.orchestrator import _flight_result_to_snapshot

        result = _make_flight_result(
            date_str="2026-06-13",
            departure_time="23:00",
            arrival_time="01:30",
        )
        snapshot = _flight_result_to_snapshot(
            result, scan_run_id=1, search_type=SearchType.ONEWAY
        )
        self.assertEqual(
            snapshot.departure_time, datetime(2026, 6, 13, 23, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(
            snapshot.arrival_time, datetime(2026, 6, 14, 1, 30, tzinfo=timezone.utc)
        )


class TestRunRoundtripPhase(unittest.TestCase):
    @patch(f"{MODULE}.search_one_way")
    def test_roundtrip_phase_is_noop(self, mock_search):
        """Verifies no API calls made, returns 0."""
        from flight_watcher.orchestrator import _run_roundtrip_phase

        mock_session = MagicMock()
        mock_scan_run = MagicMock()
        mock_config = _make_config()

        result = _run_roundtrip_phase(
            mock_session,
            mock_scan_run,
            mock_config,
            ["2026-06-13"],
            ["2026-06-28"],
        )
        self.assertEqual(result, 0)
        mock_search.assert_not_called()


class TestCursorResumption(unittest.TestCase):
    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run")
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_cursor_resumption_skips_completed_dates(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """Dates at or before cursor are skipped."""
        from flight_watcher.models import ScanStatus, SearchResult

        mock_search.return_value = SearchResult.success(1)

        mock_expand.return_value = (
            ["2026-06-13", "2026-06-14", "2026-06-15"],
            ["2026-06-28"],
        )

        # Resumable run with cursor at 2026-06-14
        resumable = _make_scan_run(
            id=10,
            status=ScanStatus.FAILED,
            last_successful_date=date(2026, 6, 14),
        )
        mock_find.return_value = resumable
        config = _make_config()

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_scan

        run_scan(config)

        # Only 2026-06-15 and 2026-06-28 remain (2 dates × 2 directions = 4 calls)
        self.assertEqual(mock_search.call_count, 4)


class TestSearchAndStoreOneway(unittest.TestCase):
    @patch(f"{MODULE}.search_one_way")
    def test_search_and_store_oneway_calls_search_and_stores_snapshots(
        self, mock_search_one_way
    ):
        """_search_and_store_oneway converts FlightResult list to PriceSnapshot list and calls add_all."""
        from flight_watcher.models import PriceSnapshot, SearchType
        from flight_watcher.orchestrator import _search_and_store_oneway

        flight_result = _make_flight_result(
            origin="GRU",
            destination="GIG",
            date_str="2026-06-13",
            price=450,
            airline="LATAM",
            duration_min=90,
            stops=0,
            departure_time="08:00",
            arrival_time="09:30",
        )
        from flight_watcher.models import SearchResult

        mock_search_one_way.return_value = SearchResult.success([flight_result])

        mock_session = MagicMock()
        scan_run = _make_scan_run(id=7)

        result = _search_and_store_oneway(
            mock_session, scan_run, "GRU", "GIG", "2026-06-13"
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.data, 1)
        mock_session.add_all.assert_called_once()
        added = mock_session.add_all.call_args[0][0]
        self.assertEqual(len(added), 1)
        snapshot = added[0]
        self.assertIsInstance(snapshot, PriceSnapshot)
        self.assertEqual(snapshot.scan_run_id, 7)
        self.assertEqual(snapshot.origin, "GRU")
        self.assertEqual(snapshot.destination, "GIG")
        self.assertEqual(snapshot.price, Decimal(450))
        self.assertEqual(snapshot.brand, "ECONOMY")
        self.assertEqual(snapshot.search_type, SearchType.ONEWAY)
        self.assertEqual(snapshot.flight_date, date(2026, 6, 13))


class TestFailureAwareCursorAdvancement(unittest.TestCase):
    def _setup_session_and_scan_run(self, mock_get_session):
        from flight_watcher.models import ScanRun

        captured = {}
        mock_session = MagicMock()

        def add_side_effect(obj):
            if isinstance(obj, ScanRun):
                obj.id = 1
                captured["scan_run"] = obj

        mock_session.add.side_effect = add_side_effect
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        return mock_session, captured

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_blocked_halts_scan_and_does_not_advance_cursor(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """BLOCKED failure raises SearchFailedError and cursor is NOT advanced."""
        from flight_watcher.errors import ErrorCategory, SearchFailedError
        from flight_watcher.models import SearchResult, ScanStatus

        mock_expand.return_value = (["2026-06-13", "2026-06-14"], ["2026-06-28"])
        mock_search.return_value = SearchResult.failure(
            error="403 Forbidden", error_category=ErrorCategory.BLOCKED
        )
        config = _make_config()
        mock_session, captured = self._setup_session_and_scan_run(mock_get_session)

        from flight_watcher.orchestrator import run_scan

        with self.assertRaises(SearchFailedError):
            run_scan(config)

        self.assertEqual(mock_search.call_count, 1)
        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].status, ScanStatus.FAILED)
        self.assertIsNone(captured["scan_run"].last_successful_date)
        mock_session.rollback.assert_called_once()

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_network_error_halts_scan_and_does_not_advance_cursor(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """NETWORK_ERROR failure raises SearchFailedError and cursor is NOT advanced."""
        from flight_watcher.errors import ErrorCategory, SearchFailedError
        from flight_watcher.models import SearchResult, ScanStatus

        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        mock_search.return_value = SearchResult.failure(
            error="Connection reset", error_category=ErrorCategory.NETWORK_ERROR
        )
        config = _make_config()
        mock_session, captured = self._setup_session_and_scan_run(mock_get_session)

        from flight_watcher.orchestrator import run_scan

        with self.assertRaises(SearchFailedError):
            run_scan(config)

        self.assertEqual(mock_search.call_count, 1)
        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].status, ScanStatus.FAILED)
        self.assertIsNone(captured["scan_run"].last_successful_date)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_rate_limited_halts_scan_and_does_not_advance_cursor(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """RATE_LIMITED failure raises SearchFailedError and cursor is NOT advanced."""
        from flight_watcher.errors import ErrorCategory, SearchFailedError
        from flight_watcher.models import SearchResult, ScanStatus

        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        mock_search.return_value = SearchResult.failure(
            error="429 Too Many Requests", error_category=ErrorCategory.RATE_LIMITED
        )
        config = _make_config()
        mock_session, captured = self._setup_session_and_scan_run(mock_get_session)

        from flight_watcher.orchestrator import run_scan

        with self.assertRaises(SearchFailedError):
            run_scan(config)

        self.assertEqual(mock_search.call_count, 1)
        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].status, ScanStatus.FAILED)
        self.assertIsNone(captured["scan_run"].last_successful_date)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_page_error_advances_cursor_and_scan_completes(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """PAGE_ERROR (skip_item=True) advances cursor and scan completes."""
        from flight_watcher.errors import ErrorCategory
        from flight_watcher.models import SearchResult, ScanStatus

        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        mock_search.return_value = SearchResult.failure(
            error="Element not found", error_category=ErrorCategory.PAGE_ERROR
        )
        config = _make_config()
        mock_session, captured = self._setup_session_and_scan_run(mock_get_session)

        from flight_watcher.orchestrator import run_scan

        run_scan(config)  # should not raise

        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].status, ScanStatus.COMPLETED)
        # Both dates processed — cursor advanced to last date
        self.assertEqual(captured["scan_run"].last_successful_date, date(2026, 6, 28))

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_empty_success_advances_cursor(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """SearchResult.success with 0 results (no flights) advances cursor — regression guard."""
        from flight_watcher.models import SearchResult, ScanStatus

        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        mock_search.return_value = SearchResult.success(0)
        config = _make_config()
        mock_session, captured = self._setup_session_and_scan_run(mock_get_session)

        from flight_watcher.orchestrator import run_scan

        run_scan(config)

        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].status, ScanStatus.COMPLETED)
        self.assertEqual(captured["scan_run"].last_successful_date, date(2026, 6, 28))

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_outbound_blocked_short_circuits_return_search(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """When outbound fails with BLOCKED, return search is not attempted."""
        from flight_watcher.errors import ErrorCategory, SearchFailedError
        from flight_watcher.models import SearchResult, ScanRun

        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        mock_search.return_value = SearchResult.failure(
            error="403 Forbidden", error_category=ErrorCategory.BLOCKED
        )
        config = _make_config()
        mock_session, captured = self._setup_session_and_scan_run(mock_get_session)

        from flight_watcher.orchestrator import run_scan

        with self.assertRaises(SearchFailedError):
            run_scan(config)

        # Only one call: outbound for the first date (short-circuited before return)
        self.assertEqual(mock_search.call_count, 1)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_partial_progress_preserved_on_mid_scan_failure(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """Dates 1-2 succeed (committed); date 3 fails. Commit called 3 times total."""
        from flight_watcher.errors import ErrorCategory, SearchFailedError
        from flight_watcher.models import SearchResult, ScanStatus

        mock_expand.return_value = (["2026-06-13", "2026-06-14", "2026-06-15"], [])
        mock_search.side_effect = [
            SearchResult.success(2),  # date 1 out
            SearchResult.success(2),  # date 1 return
            SearchResult.success(2),  # date 2 out
            SearchResult.success(2),  # date 2 return
            SearchResult.failure(
                error="429 Too Many Requests",
                error_category=ErrorCategory.RATE_LIMITED,
            ),  # date 3 out — halts scan
        ]
        config = _make_config()
        mock_session, captured = self._setup_session_and_scan_run(mock_get_session)

        from flight_watcher.orchestrator import run_scan

        with self.assertRaises(SearchFailedError):
            run_scan(config)

        # 1 initial ScanRun commit + 2 per-date commits + 1 FAILED status commit
        self.assertEqual(mock_session.commit.call_count, 4)
        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].last_successful_date, date(2026, 6, 14))
        self.assertEqual(captured["scan_run"].status, ScanStatus.FAILED)
        mock_session.rollback.assert_called_once()

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}._find_resumable_run", return_value=None)
    @patch(f"{MODULE}._search_and_store_oneway")
    @patch(f"{MODULE}.random_delay")
    @patch(f"{MODULE}.expand_dates")
    def test_outbound_succeeds_return_rate_limited_cursor_not_advanced(
        self, mock_expand, mock_delay, mock_search, mock_find, mock_get_session
    ):
        """When outbound succeeds but return fails with RATE_LIMITED, cursor is NOT advanced."""
        from flight_watcher.errors import ErrorCategory, SearchFailedError
        from flight_watcher.models import SearchResult, ScanStatus

        mock_expand.return_value = (["2026-06-13"], ["2026-06-28"])
        mock_search.side_effect = [
            SearchResult.success(2),  # outbound GRU→GIG succeeds
            SearchResult.failure(
                error="429 Too Many Requests", error_category=ErrorCategory.RATE_LIMITED
            ),  # return GIG→GRU fails
        ]
        config = _make_config()
        mock_session, captured = self._setup_session_and_scan_run(mock_get_session)

        from flight_watcher.orchestrator import run_scan

        with self.assertRaises(SearchFailedError):
            run_scan(config)

        self.assertIn("scan_run", captured)
        self.assertEqual(captured["scan_run"].status, ScanStatus.FAILED)
        self.assertIsNone(captured["scan_run"].last_successful_date)


def _make_config_row(id=1, retry_count=0, needs_attention=False):
    from datetime import date

    row = MagicMock()
    row.id = id
    row.origin = "GRU"
    row.destination = "GIG"
    row.must_arrive_by = date(2026, 6, 21)
    row.must_stay_until = date(2026, 6, 28)
    row.max_trip_days = 15
    row.retry_count = retry_count
    row.needs_attention = needs_attention
    return row


class TestRunRetryScan(unittest.TestCase):
    def setUp(self):
        import flight_watcher.scheduler as sched_mod

        sched_mod._scheduler = None

    def tearDown(self):
        import flight_watcher.scheduler as sched_mod

        sched_mod._scheduler = None

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    @patch("flight_watcher.scheduler.cancel_retry_job")
    def test_success_resets_retry_count_and_cancels_job(
        self, mock_cancel, mock_run_scan, mock_get_session
    ):
        config_row = _make_config_row(id=1, retry_count=3)
        mock_session = MagicMock()
        mock_session.get.return_value = config_row
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_retry_scan

        run_retry_scan(1)

        mock_run_scan.assert_called_once()
        self.assertEqual(config_row.retry_count, 0)
        mock_cancel.assert_called_once_with(1)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    @patch("flight_watcher.scheduler.cancel_retry_job")
    def test_failure_under_max_increments_retry_count(
        self, mock_cancel, mock_run_scan, mock_get_session
    ):
        config_row = _make_config_row(id=1, retry_count=0)
        mock_session = MagicMock()
        mock_session.get.return_value = config_row
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_run_scan.side_effect = RuntimeError("scan failed")

        from flight_watcher.orchestrator import run_retry_scan

        run_retry_scan(1)

        self.assertEqual(config_row.retry_count, 1)
        self.assertFalse(config_row.needs_attention)
        mock_cancel.assert_not_called()

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    @patch("flight_watcher.scheduler.cancel_retry_job")
    @patch("flight_watcher.scheduler.RETRY_MAX_ATTEMPTS", 3)
    def test_failure_at_max_sets_needs_attention_and_cancels_job(
        self, mock_cancel, mock_run_scan, mock_get_session
    ):
        # retry_count starts at 2; after increment it will be 3 == RETRY_MAX_ATTEMPTS
        config_row = _make_config_row(id=1, retry_count=2)
        mock_session = MagicMock()
        mock_session.get.return_value = config_row
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_run_scan.side_effect = RuntimeError("scan failed")

        from flight_watcher.orchestrator import run_retry_scan

        run_retry_scan(1)

        self.assertEqual(config_row.retry_count, 3)
        self.assertTrue(config_row.needs_attention)
        mock_cancel.assert_called_once_with(1)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    def test_missing_config_logs_warning_and_returns(
        self, mock_run_scan, mock_get_session
    ):
        mock_session = MagicMock()
        mock_session.get.return_value = None
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_retry_scan

        with self.assertLogs("flight_watcher.orchestrator", level="WARNING") as cm:
            run_retry_scan(99)

        mock_run_scan.assert_not_called()
        self.assertTrue(any("99" in line for line in cm.output))

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    def test_needs_attention_config_logs_warning_and_returns(
        self, mock_run_scan, mock_get_session
    ):
        config_row = _make_config_row(id=1, needs_attention=True)
        mock_session = MagicMock()
        mock_session.get.return_value = config_row
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_retry_scan

        with self.assertLogs("flight_watcher.orchestrator", level="WARNING") as cm:
            run_retry_scan(1)

        mock_run_scan.assert_not_called()
        self.assertTrue(any("needs_attention" in line for line in cm.output))


class TestRunAllScansRetryIntegration(unittest.TestCase):
    def _make_orm_row(self, id=1, retry_count=0):
        row = MagicMock()
        row.id = id
        row.origin = "GRU"
        row.destination = "GIG"
        row.must_arrive_by = date(2026, 6, 21)
        row.must_stay_until = date(2026, 6, 28)
        row.max_trip_days = 15
        row.retry_count = retry_count
        return row

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    @patch("flight_watcher.scheduler.cancel_retry_job")
    def test_scan_success_calls_cancel_retry_job(
        self, mock_cancel, mock_run_scan, mock_get_session
    ):
        orm1 = self._make_orm_row(id=1)
        mock_session = MagicMock()
        mock_session.scalars.return_value.all.return_value = [orm1]
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.orchestrator import run_all_scans

        run_all_scans()

        mock_cancel.assert_called_once_with(1)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    @patch("flight_watcher.scheduler.register_retry_job")
    def test_scan_failure_calls_register_retry_job(
        self, mock_register, mock_run_scan, mock_get_session
    ):
        orm1 = self._make_orm_row(id=2)
        mock_session = MagicMock()
        mock_session.scalars.return_value.all.return_value = [orm1]
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_run_scan.side_effect = RuntimeError("scan failed")

        from flight_watcher.orchestrator import run_all_scans

        run_all_scans()  # should not raise

        mock_register.assert_called_once_with(2)

    @patch(f"{MODULE}.get_session")
    @patch(f"{MODULE}.run_scan")
    @patch("flight_watcher.scheduler.cancel_retry_job")
    @patch("flight_watcher.scheduler.register_retry_job")
    def test_multiple_configs_correct_retry_jobs(
        self, mock_register, mock_cancel, mock_run_scan, mock_get_session
    ):
        orm1 = self._make_orm_row(id=1)
        orm2 = self._make_orm_row(id=2)
        mock_session = MagicMock()
        mock_session.scalars.return_value.all.return_value = [orm1, orm2]
        mock_get_session.return_value.__enter__ = lambda s: mock_session
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        # Config 1 succeeds, config 2 fails
        mock_run_scan.side_effect = [None, RuntimeError("boom")]

        from flight_watcher.orchestrator import run_all_scans

        run_all_scans()

        mock_cancel.assert_called_once_with(1)
        mock_register.assert_called_once_with(2)
