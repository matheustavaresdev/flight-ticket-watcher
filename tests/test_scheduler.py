import logging
import unittest
from unittest.mock import MagicMock, patch

SCHED_MODULE = "flight_watcher.scheduler"


def _make_mock_scheduler():
    mock = MagicMock()
    mock.running = True
    return mock


class TestCreateScheduler(unittest.TestCase):
    @patch(f"{SCHED_MODULE}.get_database_url", return_value="postgresql+psycopg://user:pass@localhost/db")
    @patch(f"{SCHED_MODULE}.SQLAlchemyJobStore")
    @patch(f"{SCHED_MODULE}.BackgroundScheduler")
    def test_create_scheduler_returns_background_scheduler(self, mock_bg, mock_store, mock_url):
        from flight_watcher.scheduler import create_scheduler
        result = create_scheduler()
        mock_bg.assert_called_once()
        self.assertIsNotNone(result)

    @patch(f"{SCHED_MODULE}.get_database_url", return_value="postgresql+psycopg://user:pass@localhost/db")
    @patch(f"{SCHED_MODULE}.SQLAlchemyJobStore")
    @patch(f"{SCHED_MODULE}.BackgroundScheduler")
    def test_create_scheduler_uses_database_url(self, mock_bg, mock_store, mock_url):
        from flight_watcher.scheduler import create_scheduler
        create_scheduler()
        mock_store.assert_called_once_with(
            url="postgresql+psycopg://user:pass@localhost/db",
            tablename="apscheduler_jobs",
        )

    @patch(f"{SCHED_MODULE}.get_database_url", return_value="postgresql+psycopg://user:pass@localhost/db")
    @patch(f"{SCHED_MODULE}.SQLAlchemyJobStore")
    @patch(f"{SCHED_MODULE}.BackgroundScheduler")
    def test_scheduler_configured_with_utc(self, mock_bg, mock_store, mock_url):
        from flight_watcher.scheduler import create_scheduler
        from pytz import utc
        create_scheduler()
        call_kwargs = mock_bg.call_args[1]
        self.assertEqual(call_kwargs["timezone"], utc)

    @patch(f"{SCHED_MODULE}.get_database_url", return_value="postgresql+psycopg://user:pass@localhost/db")
    @patch(f"{SCHED_MODULE}.SQLAlchemyJobStore")
    @patch(f"{SCHED_MODULE}.BackgroundScheduler")
    def test_scheduler_job_defaults(self, mock_bg, mock_store, mock_url):
        from flight_watcher.scheduler import create_scheduler
        create_scheduler()
        call_kwargs = mock_bg.call_args[1]
        job_defaults = call_kwargs["job_defaults"]
        self.assertTrue(job_defaults["coalesce"])
        self.assertEqual(job_defaults["max_instances"], 1)


class TestGetScheduler(unittest.TestCase):
    def setUp(self):
        import flight_watcher.scheduler as sched_mod
        sched_mod._scheduler = None

    def tearDown(self):
        import flight_watcher.scheduler as sched_mod
        sched_mod._scheduler = None

    @patch(f"{SCHED_MODULE}.create_scheduler")
    def test_get_scheduler_returns_singleton(self, mock_create):
        mock_create.return_value = MagicMock()
        from flight_watcher.scheduler import get_scheduler
        s1 = get_scheduler()
        s2 = get_scheduler()
        self.assertIs(s1, s2)
        mock_create.assert_called_once()

    @patch(f"{SCHED_MODULE}.create_scheduler")
    def test_get_scheduler_resets_after_stop(self, mock_create):
        first = MagicMock()
        second = MagicMock()
        mock_create.side_effect = [first, second]

        from flight_watcher.scheduler import get_scheduler, stop_scheduler
        s1 = get_scheduler()
        stop_scheduler()
        s2 = get_scheduler()
        self.assertIsNot(s1, s2)


class TestEventListeners(unittest.TestCase):
    def test_on_job_executed_logs_info(self):
        from flight_watcher.scheduler import _on_job_executed
        event = MagicMock()
        event.job_id = "test_job"
        event.retval = "result"
        with self.assertLogs("flight_watcher.scheduler", level="INFO") as cm:
            _on_job_executed(event)
        self.assertTrue(any("test_job" in line for line in cm.output))

    def test_on_job_error_logs_error(self):
        from flight_watcher.scheduler import _on_job_error
        event = MagicMock()
        event.job_id = "test_job"
        event.exception = ValueError("boom")
        event.traceback = None
        with self.assertLogs("flight_watcher.scheduler", level="ERROR") as cm:
            _on_job_error(event)
        self.assertTrue(any("test_job" in line for line in cm.output))


class TestStartStopScheduler(unittest.TestCase):
    def setUp(self):
        import flight_watcher.scheduler as sched_mod
        sched_mod._scheduler = None

    def tearDown(self):
        import flight_watcher.scheduler as sched_mod
        sched_mod._scheduler = None

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_start_scheduler_calls_start(self, mock_get):
        mock_sched = MagicMock()
        mock_get.return_value = mock_sched
        from flight_watcher.scheduler import start_scheduler
        start_scheduler()
        mock_sched.start.assert_called_once()

    @patch(f"{SCHED_MODULE}.create_scheduler")
    def test_stop_scheduler_calls_shutdown_with_wait(self, mock_create):
        mock_sched = MagicMock()
        mock_create.return_value = mock_sched
        from flight_watcher.scheduler import get_scheduler, stop_scheduler
        get_scheduler()  # populate singleton
        stop_scheduler()
        mock_sched.shutdown.assert_called_once_with(wait=True)
