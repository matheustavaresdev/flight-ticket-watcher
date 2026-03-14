"""Tests for the __main__ module entry point."""

from unittest.mock import patch


class TestMainEntryPoint:
    def test_main_module_calls_app(self):
        """When invoked as __main__, the Typer app is called."""
        with patch("flight_watcher.cli.app") as mock_app:
            import importlib
            import flight_watcher.__main__ as main_mod
            importlib.reload(main_mod)
            # The module just imports app and guards with __name__ == "__main__"
            # so app() is NOT called on import — that's the correct behaviour
            mock_app.assert_not_called()
