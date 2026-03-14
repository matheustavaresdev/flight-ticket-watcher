"""Tests for the flight_watcher CLI commands."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from flight_watcher.cli import app
from flight_watcher.models import SearchConfig


def make_session_mock(session_mock=None):
    """Return a mock that acts as a context manager yielding session_mock."""
    if session_mock is None:
        session_mock = MagicMock()
    ctx_mock = MagicMock()
    ctx_mock.__enter__ = MagicMock(return_value=session_mock)
    ctx_mock.__exit__ = MagicMock(return_value=False)
    get_session_mock = MagicMock(return_value=ctx_mock)
    return get_session_mock, session_mock


class TestConfigAdd:
    def test_valid_inputs_creates_search_config(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()

        # Simulate session.flush() setting the id on the object passed to session.add()
        def flush_side_effect():
            # Find the SearchConfig object that was added and set its id
            call_args = session_mock.add.call_args
            if call_args:
                obj = call_args[0][0]
                obj.id = 42

        session_mock.flush.side_effect = flush_side_effect

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(
                app,
                ["config", "add", "FOR", "MIA", "2026-06-21", "2026-06-28", "--max-days", "15"],
            )

        assert result.exit_code == 0, result.output
        session_mock.add.assert_called_once()
        added_obj = session_mock.add.call_args[0][0]
        assert isinstance(added_obj, SearchConfig)
        assert added_obj.origin == "FOR"
        assert added_obj.destination == "MIA"
        assert added_obj.must_arrive_by == date(2026, 6, 21)
        assert added_obj.must_stay_until == date(2026, 6, 28)
        assert added_obj.max_trip_days == 15
        assert added_obj.active is True
        assert "42" in result.output

    def test_invalid_iata_code_too_long(self):
        runner = CliRunner()
        get_session_mock, _ = make_session_mock()

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(
                app,
                ["config", "add", "ABCD", "MIA", "2026-06-21", "2026-06-28", "--max-days", "15"],
            )

        assert result.exit_code != 0
        assert "IATA" in result.output or "invalid" in result.output.lower()

    def test_invalid_iata_code_numeric(self):
        runner = CliRunner()
        get_session_mock, _ = make_session_mock()

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(
                app,
                ["config", "add", "12", "MIA", "2026-06-21", "2026-06-28", "--max-days", "15"],
            )

        assert result.exit_code != 0
        assert "IATA" in result.output or "invalid" in result.output.lower()

    def test_stay_until_before_arrive_by_raises_error(self):
        runner = CliRunner()
        get_session_mock, _ = make_session_mock()

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(
                app,
                # must_stay_until (June 21) is before must_arrive_by (June 28)
                [
                    "config",
                    "add",
                    "FOR",
                    "MIA",
                    "2026-06-28",
                    "2026-06-21",
                    "--max-days",
                    "15",
                ],
            )

        assert result.exit_code != 0
        assert "must_stay_until" in result.output or "Error" in result.output

    def test_max_days_too_small_raises_error(self):
        """max_days=1 but the minimum stay is 7 days (June 21 → June 28)."""
        runner = CliRunner()
        get_session_mock, _ = make_session_mock()

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(
                app,
                ["config", "add", "FOR", "MIA", "2026-06-21", "2026-06-28", "--max-days", "1"],
            )

        assert result.exit_code != 0
        assert "Error" in result.output

    def test_lowercase_iata_codes_are_uppercased(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()

        def flush_side_effect():
            call_args = session_mock.add.call_args
            if call_args:
                call_args[0][0].id = 1

        session_mock.flush.side_effect = flush_side_effect

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(
                app,
                ["config", "add", "for", "mia", "2026-06-21", "2026-06-28", "--max-days", "15"],
            )

        assert result.exit_code == 0, result.output
        added_obj = session_mock.add.call_args[0][0]
        assert added_obj.origin == "FOR"
        assert added_obj.destination == "MIA"


class TestConfigList:
    def _make_config(
        self, id, origin, dest, arrive_by, stay_until, max_days, active=True
    ):
        cfg = MagicMock(spec=SearchConfig)
        cfg.id = id
        cfg.origin = origin
        cfg.destination = dest
        cfg.must_arrive_by = arrive_by
        cfg.must_stay_until = stay_until
        cfg.max_trip_days = max_days
        cfg.active = active
        return cfg

    def test_list_shows_active_configs_by_default(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()

        active_cfg = self._make_config(
            1, "FOR", "MIA", date(2026, 6, 21), date(2026, 6, 28), 15, active=True
        )

        # When include_all=False, only active configs are returned
        session_mock.execute.return_value.scalars.return_value.all.return_value = [
            active_cfg
        ]

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(app, ["config", "list"])

        assert result.exit_code == 0, result.output
        assert "FOR" in result.output
        assert "MIA" in result.output
        assert "GRU" not in result.output
        # Header should be present
        assert "ID" in result.output
        assert "Origin" in result.output

    def test_list_all_includes_inactive_configs(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()

        active_cfg = self._make_config(
            1, "FOR", "MIA", date(2026, 6, 21), date(2026, 6, 28), 15, active=True
        )
        inactive_cfg = self._make_config(
            2, "GRU", "LIS", date(2026, 7, 1), date(2026, 7, 10), 20, active=False
        )

        session_mock.execute.return_value.scalars.return_value.all.return_value = [
            active_cfg,
            inactive_cfg,
        ]

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(app, ["config", "list", "--all"])

        assert result.exit_code == 0, result.output
        assert "FOR" in result.output
        assert "GRU" in result.output
        assert "LIS" in result.output


class TestConfigToggle:
    def test_valid_id_toggles_active_false(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()

        cfg = MagicMock(spec=SearchConfig)
        cfg.id = 5
        cfg.active = True
        session_mock.get.return_value = cfg

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(app, ["config", "toggle", "5"])

        assert result.exit_code == 0, result.output
        assert cfg.active is False
        session_mock.get.assert_called_once_with(SearchConfig, 5)
        assert "5" in result.output
        assert "inactive" in result.output.lower()

    def test_nonexistent_id_returns_error(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()

        session_mock.get.return_value = None

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(app, ["config", "toggle", "999"])

        assert result.exit_code != 0
        assert "999" in result.output
        assert "not found" in result.output.lower()


class TestVerboseFlag:
    def test_verbose_flag_sets_debug(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()
        session_mock.execute.return_value.scalars.return_value.all.return_value = []

        with patch("flight_watcher.cli.config.get_session", get_session_mock):
            result = runner.invoke(app, ["--verbose", "config", "list"])

        assert result.exit_code == 0, result.output


class TestHealthCommand:
    def test_health_shows_status(self):
        runner = CliRunner()
        get_session_mock, _ = make_session_mock()

        breaker_mock = MagicMock()
        breaker_mock.status_info.return_value = {
            "state": "closed",
            "consecutive_failures": 0,
        }

        with (
            patch("flight_watcher.db.get_session", get_session_mock),
            patch("flight_watcher.circuit_breaker.get_breaker", return_value=breaker_mock),
        ):
            result = runner.invoke(app, ["health"])

        assert "[OK]" in result.output, result.output


class TestRunsCommand:
    def test_runs_list_shows_recent(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()
        session_mock.execute.return_value.scalars.return_value.all.return_value = []

        with patch("flight_watcher.cli.runs.get_session", get_session_mock):
            result = runner.invoke(app, ["runs", "list"])

        assert result.exit_code == 0, result.output


class TestSearchCommands:
    def test_search_latam_invokes_scraper(self):
        runner = CliRunner()
        mock_data = MagicMock()
        mock_offers = [MagicMock()]

        with (
            patch("flight_watcher.latam_scraper.search_latam_oneway", return_value=mock_data) as mock_search,
            patch("flight_watcher.latam_scraper.parse_offers", return_value=mock_offers),
            patch("flight_watcher.display.print_offers"),
        ):
            result = runner.invoke(
                app,
                ["search", "latam", "--origin", "GRU", "--dest", "FOR", "--out", "2026-04-12"],
            )

        assert result.exit_code == 0, result.output
        mock_search.assert_called_once()

    def test_search_latam_rejects_invalid_iata(self):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["search", "latam", "--origin", "GRUU", "--dest", "GRU", "--out", "2026-04-01"],
        )
        assert result.exit_code != 0
        assert "Invalid IATA" in result.output

    def test_search_latam_rejects_invalid_date(self):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["search", "latam", "--origin", "GRU", "--dest", "CGH", "--out", "2026/04/01"],
        )
        assert result.exit_code != 0
        assert "Invalid date" in result.output

    def test_search_fast_rejects_invalid_iata(self):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["search", "fast", "--origin", "GRUU", "--dest", "GRU", "--date", "2026-04-01"],
        )
        assert result.exit_code != 0
        assert "Invalid IATA" in result.output

    def test_search_fast_rejects_invalid_date(self):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["search", "fast", "--origin", "GRU", "--dest", "CGH", "--date", "2026/04/01"],
        )
        assert result.exit_code != 0
        assert "Invalid date" in result.output

    def test_search_fast_invokes_scanner(self):
        runner = CliRunner()
        mock_results = [MagicMock()]

        with (
            patch("flight_watcher.scanner.search_one_way", return_value=mock_results) as mock_search,
            patch("flight_watcher.display.print_results"),
        ):
            result = runner.invoke(
                app,
                ["search", "fast", "--origin", "GRU", "--dest", "FOR", "--date", "2026-04-12"],
            )

        assert result.exit_code == 0, result.output
        mock_search.assert_called_once()


class TestReport:
    def _make_config(self, config_id=1, origin="GRU", destination="FOR"):
        cfg = MagicMock(spec=SearchConfig)
        cfg.id = config_id
        cfg.origin = origin
        cfg.destination = destination
        return cfg

    def _make_snapshot(self, flight_date=None, flight_code="LA3456", brand="LIGHT", price="450.00", currency="BRL", stops=0, duration_min=180):
        from datetime import datetime
        s = MagicMock()
        s.flight_date = flight_date or date(2026, 6, 21)
        s.flight_code = flight_code
        s.brand = brand
        s.price = Decimal(price)
        s.currency = currency
        s.stops = stops
        s.duration_min = duration_min
        fd = s.flight_date
        s.departure_time = datetime(fd.year, fd.month, fd.day, 8, 0)
        s.arrival_time = datetime(fd.year, fd.month, fd.day, 11, 0)
        return s

    def test_report_show_prints_top_flights(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()
        cfg = self._make_config()
        session_mock.get.return_value = cfg
        snap = self._make_snapshot()

        with patch("flight_watcher.cli.report.get_session", get_session_mock), \
             patch("flight_watcher.cli.report.get_latest_snapshots", return_value=[snap]), \
             patch("flight_watcher.cli.report.best_combinations", return_value=[]), \
             patch("flight_watcher.cli.report.roundtrip_vs_oneway", return_value=[]):
            result = runner.invoke(app, ["report", "show", "1"])

        assert result.exit_code == 0, result.output
        assert "Top Flights" in result.output
        assert "LA3456" in result.output
        assert "[OK]" in result.output

    def test_report_show_prints_best_combinations(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()
        cfg = self._make_config()
        session_mock.get.return_value = cfg

        combo = {
            "outbound_date": date(2026, 6, 21),
            "return_date": date(2026, 6, 26),
            "trip_days": 5,
            "outbound_price": Decimal("450.00"),
            "return_price": Decimal("380.00"),
            "total_price": Decimal("830.00"),
            "currency": "BRL",
        }

        with patch("flight_watcher.cli.report.get_session", get_session_mock), \
             patch("flight_watcher.cli.report.get_latest_snapshots", return_value=[]), \
             patch("flight_watcher.cli.report.best_combinations", return_value=[combo]), \
             patch("flight_watcher.cli.report.roundtrip_vs_oneway", return_value=[]):
            result = runner.invoke(app, ["report", "show", "1"])

        assert result.exit_code == 0, result.output
        assert "Best by Stay Length" in result.output
        assert "2026-06-21" in result.output
        assert "830" in result.output

    def test_report_show_prints_rt_vs_ow(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()
        cfg = self._make_config()
        session_mock.get.return_value = cfg

        rt_row = {
            "outbound_date": date(2026, 6, 21),
            "return_date": date(2026, 6, 26),
            "roundtrip_total": Decimal("900.00"),
            "oneway_total": Decimal("830.00"),
            "savings_pct": 7.8,
            "recommendation": "2x one-way",
            "significant": True,
            "currency": "BRL",
        }

        with patch("flight_watcher.cli.report.get_session", get_session_mock), \
             patch("flight_watcher.cli.report.get_latest_snapshots", return_value=[]), \
             patch("flight_watcher.cli.report.best_combinations", return_value=[]), \
             patch("flight_watcher.cli.report.roundtrip_vs_oneway", return_value=[rt_row]):
            result = runner.invoke(app, ["report", "show", "1"])

        assert result.exit_code == 0, result.output
        assert "Roundtrip vs One-Way" in result.output
        assert "2x one-way" in result.output
        assert "**" in result.output

    def test_report_show_invalid_config_exits_1(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()
        session_mock.get.return_value = None

        with patch("flight_watcher.cli.report.get_session", get_session_mock):
            result = runner.invoke(app, ["report", "show", "999"])

        assert result.exit_code == 1

    def test_report_show_brand_filter(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()
        cfg = self._make_config()
        session_mock.get.return_value = cfg
        snap = self._make_snapshot(brand="LIGHT")

        with patch("flight_watcher.cli.report.get_session", get_session_mock), \
             patch("flight_watcher.cli.report.get_latest_snapshots", return_value=[snap]) as mock_snaps, \
             patch("flight_watcher.cli.report.best_combinations", return_value=[]) as mock_combos, \
             patch("flight_watcher.cli.report.roundtrip_vs_oneway", return_value=[]) as mock_rt:
            result = runner.invoke(app, ["report", "show", "1", "--brand", "LIGHT"])

        assert result.exit_code == 0, result.output
        # When --brand LIGHT is passed, all three query functions receive brand="LIGHT"
        mock_snaps.assert_called_once_with(session_mock, 1, brand="LIGHT")
        mock_combos.assert_called_once_with(session_mock, 1, brand="LIGHT", limit=None)
        mock_rt.assert_called_once_with(session_mock, 1, brand="LIGHT")

    def test_report_show_top_limits_rows(self):
        runner = CliRunner()
        get_session_mock, session_mock = make_session_mock()
        cfg = self._make_config()
        session_mock.get.return_value = cfg
        snaps = [self._make_snapshot(flight_code=f"LA{i:04d}", price=str(400 + i)) for i in range(20)]

        with patch("flight_watcher.cli.report.get_session", get_session_mock), \
             patch("flight_watcher.cli.report.get_latest_snapshots", return_value=snaps), \
             patch("flight_watcher.cli.report.best_combinations", return_value=[]), \
             patch("flight_watcher.cli.report.roundtrip_vs_oneway", return_value=[]):
            result = runner.invoke(app, ["report", "show", "1", "--top", "5"])

        assert result.exit_code == 0, result.output
        assert "Showing top 5 of" in result.output
        # LA0005-LA0019 are more expensive and must not appear when --top 5 is used.
        # Relies on price=400+i, so higher index ↔ higher price ↔ outside top-5.
        for i in range(5, 20):
            assert f"LA{i:04d}" not in result.output
