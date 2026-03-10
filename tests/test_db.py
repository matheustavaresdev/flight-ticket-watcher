import os
from unittest.mock import MagicMock, patch

import pytest


class TestGetDatabaseUrl:
    def test_builds_url_from_env_vars(self):
        env = {
            "POSTGRES_HOST": "myhost",
            "POSTGRES_PORT": "5433",
            "POSTGRES_DB": "mydb",
            "POSTGRES_USER": "myuser",
            "POSTGRES_PASSWORD": "mypass",
        }
        # Patch env vars and reimport to avoid module-level caching
        with patch.dict(os.environ, env, clear=True):
            from flight_watcher.db import get_database_url

            url = get_database_url()

        assert url == "postgresql+psycopg://myuser:mypass@myhost:5433/mydb"

    def test_database_url_override_takes_precedence(self):
        env = {
            "DATABASE_URL": "postgresql+psycopg://override:secret@otherhost:5432/otherdb",
            "POSTGRES_HOST": "shouldbeignored",
        }
        with patch.dict(os.environ, env, clear=True):
            from flight_watcher.db import get_database_url

            url = get_database_url()

        assert url == "postgresql+psycopg://override:secret@otherhost:5432/otherdb"

    def test_uses_defaults_when_no_env_vars(self):
        with patch.dict(os.environ, {}, clear=True):
            from flight_watcher.db import get_database_url

            url = get_database_url()

        assert url == "postgresql+psycopg://flight_watcher:changeme@localhost:5432/flight_watcher"


class TestGetSession:
    def test_get_session_yields_session_and_closes(self):
        mock_session = MagicMock()
        mock_session_local = MagicMock(return_value=mock_session)

        with patch("flight_watcher.db.SessionLocal", mock_session_local):
            from flight_watcher.db import get_session

            with get_session() as session:
                assert session is mock_session

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    def test_get_session_rolls_back_on_exception(self):
        mock_session = MagicMock()
        mock_session_local = MagicMock(return_value=mock_session)

        with patch("flight_watcher.db.SessionLocal", mock_session_local):
            from flight_watcher.db import get_session

            with pytest.raises(ValueError):
                with get_session():
                    raise ValueError("test error")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.commit.assert_not_called()
