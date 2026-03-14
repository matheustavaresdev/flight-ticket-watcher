"""Tests for the flight_watcher CLI commands."""

from datetime import date
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
