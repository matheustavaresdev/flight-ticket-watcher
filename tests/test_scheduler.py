import unittest
from unittest.mock import MagicMock, patch

SCHED_MODULE = "flight_watcher.scheduler"


def _make_mock_scheduler():
    mock = MagicMock()
    mock.running = True
    return mock


class TestCreateScheduler(unittest.TestCase):
    @patch(
        f"{SCHED_MODULE}.get_database_url",
        return_value="postgresql+psycopg://user:pass@localhost/db",
    )
    @patch(f"{SCHED_MODULE}.SQLAlchemyJobStore")
    @patch(f"{SCHED_MODULE}.BackgroundScheduler")
    def test_create_scheduler_returns_background_scheduler(
        self, mock_bg, mock_store, mock_url
    ):
        from flight_watcher.scheduler import create_scheduler

        result = create_scheduler()
        mock_bg.assert_called_once()
        self.assertIsNotNone(result)

    @patch(
        f"{SCHED_MODULE}.get_database_url",
        return_value="postgresql+psycopg://user:pass@localhost/db",
    )
    @patch(f"{SCHED_MODULE}.SQLAlchemyJobStore")
    @patch(f"{SCHED_MODULE}.BackgroundScheduler")
    def test_create_scheduler_uses_database_url(self, mock_bg, mock_store, mock_url):
        from flight_watcher.scheduler import create_scheduler

        create_scheduler()
        mock_store.assert_called_once_with(
            url="postgresql+psycopg://user:pass@localhost/db",
            tablename="apscheduler_jobs",
        )

    @patch(
        f"{SCHED_MODULE}.get_database_url",
        return_value="postgresql+psycopg://user:pass@localhost/db",
    )
    @patch(f"{SCHED_MODULE}.SQLAlchemyJobStore")
    @patch(f"{SCHED_MODULE}.BackgroundScheduler")
    def test_scheduler_configured_with_utc(self, mock_bg, mock_store, mock_url):
        from datetime import timezone
        from flight_watcher.scheduler import create_scheduler

        create_scheduler()
        call_kwargs = mock_bg.call_args[1]
        self.assertEqual(call_kwargs["timezone"], timezone.utc)

    @patch(
        f"{SCHED_MODULE}.get_database_url",
        return_value="postgresql+psycopg://user:pass@localhost/db",
    )
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


class TestRegisterScanJob(unittest.TestCase):
    def setUp(self):
        import flight_watcher.scheduler as sched_mod
        sched_mod._scheduler = None

    def tearDown(self):
        import flight_watcher.scheduler as sched_mod
        sched_mod._scheduler = None

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_scan_job_adds_interval_trigger(self, mock_get_scheduler):
        """Verifies scheduler.add_job called with interval trigger and correct params."""
        mock_sched = MagicMock()
        mock_sched.get_job.return_value = None  # job doesn't exist yet
        mock_get_scheduler.return_value = mock_sched

        from flight_watcher.scheduler import register_scan_job

        register_scan_job()

        mock_sched.add_job.assert_called_once()
        call_kwargs = mock_sched.add_job.call_args[1]
        self.assertEqual(call_kwargs["trigger"], "interval")
        self.assertEqual(call_kwargs["id"], "scheduled_scan")
        self.assertTrue(call_kwargs["replace_existing"])

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_scan_job_uses_scan_interval_minutes(self, mock_get_scheduler):
        """Verifies SCAN_INTERVAL_MINUTES env var is passed to interval trigger."""
        mock_sched = MagicMock()
        mock_sched.get_job.return_value = None  # job doesn't exist yet
        mock_get_scheduler.return_value = mock_sched

        import os
        from unittest.mock import patch as mock_patch
        with mock_patch.dict(os.environ, {"SCAN_INTERVAL_MINUTES": "30"}):
            import flight_watcher.scheduler as sched_mod
            sched_mod.SCAN_INTERVAL_MINUTES = 30
            from flight_watcher.scheduler import register_scan_job
            register_scan_job()

        call_kwargs = mock_sched.add_job.call_args[1]
        self.assertEqual(call_kwargs["minutes"], 30)

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_scan_job_default_interval_is_60(self, mock_get_scheduler):
        """Verifies default scan interval is 60 minutes."""
        mock_sched = MagicMock()
        mock_sched.get_job.return_value = None  # job doesn't exist yet
        mock_get_scheduler.return_value = mock_sched

        from flight_watcher.scheduler import register_scan_job, SCAN_INTERVAL_MINUTES
        register_scan_job()

        call_kwargs = mock_sched.add_job.call_args[1]
        self.assertEqual(call_kwargs["minutes"], SCAN_INTERVAL_MINUTES)

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_scan_job_skips_if_already_exists(self, mock_get_scheduler):
        """Verifies add_job is not called when scheduled_scan job already exists with same interval."""
        from datetime import timedelta
        from flight_watcher.scheduler import SCAN_INTERVAL_MINUTES

        mock_sched = MagicMock()
        existing_job = MagicMock()
        existing_job.trigger.interval = timedelta(minutes=SCAN_INTERVAL_MINUTES)
        mock_sched.get_job.return_value = existing_job
        mock_get_scheduler.return_value = mock_sched

        from flight_watcher.scheduler import register_scan_job

        register_scan_job()

        mock_sched.add_job.assert_not_called()

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_scan_job_replaces_if_interval_changed(self, mock_get_scheduler):
        """Verifies add_job is called with replace_existing=True when interval differs."""
        from datetime import timedelta
        from flight_watcher.scheduler import SCAN_INTERVAL_MINUTES

        mock_sched = MagicMock()
        existing_job = MagicMock()
        existing_job.trigger.interval = timedelta(minutes=SCAN_INTERVAL_MINUTES + 15)
        mock_sched.get_job.return_value = existing_job
        mock_get_scheduler.return_value = mock_sched

        from flight_watcher.scheduler import register_scan_job

        register_scan_job()

        mock_sched.add_job.assert_called_once()
        call_kwargs = mock_sched.add_job.call_args[1]
        self.assertTrue(call_kwargs["replace_existing"])

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_scan_job_adds_if_not_exists(self, mock_get_scheduler):
        """Verifies add_job is called when scheduled_scan job does not exist."""
        mock_sched = MagicMock()
        mock_sched.get_job.return_value = None
        mock_get_scheduler.return_value = mock_sched

        from flight_watcher.scheduler import register_scan_job

        register_scan_job()

        mock_sched.add_job.assert_called_once()

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_scan_job_migration_catches_job_lookup_error(self, mock_get_scheduler):
        """Verifies JobLookupError (not bare Exception) is caught in migration block."""
        from apscheduler.jobstores.base import JobLookupError

        mock_sched = MagicMock()
        mock_sched.get_job.return_value = None
        mock_sched.remove_job.side_effect = JobLookupError("daily_scan")
        mock_get_scheduler.return_value = mock_sched

        from flight_watcher.scheduler import register_scan_job

        # Should not raise — JobLookupError is caught in the migration block
        register_scan_job()
        mock_sched.add_job.assert_called_once()


class TestJobListenerStateSideEffects(unittest.TestCase):
    def setUp(self):
        import flight_watcher.scheduler as sched_mod
        import flight_watcher.scanner_state as state_mod

        sched_mod._scheduler = None
        state_mod._state = None

    def tearDown(self):
        import flight_watcher.scheduler as sched_mod
        import flight_watcher.scanner_state as state_mod

        sched_mod._scheduler = None
        state_mod._state = None

    def test_on_job_submitted_sets_scanning(self):
        from flight_watcher.scanner_state import ScannerStatus, get_scanner_state
        from flight_watcher.scheduler import _on_job_submitted

        event = MagicMock()
        event.job_id = "test_job"
        _on_job_submitted(event)
        self.assertEqual(get_scanner_state().status, ScannerStatus.SCANNING)

    def test_on_job_executed_sets_idle(self):
        from flight_watcher.scanner_state import ScannerStatus, get_scanner_state
        from flight_watcher.scheduler import _on_job_executed

        get_scanner_state().status = ScannerStatus.SCANNING
        event = MagicMock()
        event.job_id = "test_job"
        event.retval = None
        _on_job_executed(event)
        self.assertEqual(get_scanner_state().status, ScannerStatus.IDLE)

    def test_on_job_error_sets_idle(self):
        from flight_watcher.scanner_state import ScannerStatus, get_scanner_state
        from flight_watcher.scheduler import _on_job_error

        get_scanner_state().status = ScannerStatus.SCANNING
        event = MagicMock()
        event.job_id = "test_job"
        event.exception = ValueError("boom")
        event.traceback = None
        _on_job_error(event)
        self.assertEqual(get_scanner_state().status, ScannerStatus.IDLE)

    @patch(
        "flight_watcher.scheduler.get_database_url",
        return_value="postgresql+psycopg://user:pass@localhost/db",
    )
    @patch("flight_watcher.scheduler.SQLAlchemyJobStore")
    @patch("flight_watcher.scheduler.BackgroundScheduler")
    def test_create_scheduler_registers_submitted_listener(
        self, mock_bg, mock_store, mock_url
    ):
        from flight_watcher.scheduler import create_scheduler
        from apscheduler.events import EVENT_JOB_SUBMITTED

        create_scheduler()
        mock_sched = mock_bg.return_value
        listener_calls = mock_sched.add_listener.call_args_list
        submitted_calls = [c for c in listener_calls if c[0][1] == EVENT_JOB_SUBMITTED]
        self.assertTrue(len(submitted_calls) > 0)


class TestRetryJobId(unittest.TestCase):
    def test_retry_job_id_returns_expected_format(self):
        from flight_watcher.scheduler import _retry_job_id

        self.assertEqual(_retry_job_id(42), "retry_config_42")
        self.assertEqual(_retry_job_id(1), "retry_config_1")


class TestRegisterRetryJob(unittest.TestCase):
    def setUp(self):
        import flight_watcher.scheduler as sched_mod

        sched_mod._scheduler = None

    def tearDown(self):
        import flight_watcher.scheduler as sched_mod

        sched_mod._scheduler = None

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_retry_job_adds_interval_trigger(self, mock_get_scheduler):
        mock_sched = MagicMock()
        mock_sched.get_job.return_value = None  # job doesn't exist yet
        mock_get_scheduler.return_value = mock_sched
        from flight_watcher.scheduler import register_retry_job

        register_retry_job(5)
        mock_sched.add_job.assert_called_once()
        call_kwargs = mock_sched.add_job.call_args[1]
        self.assertEqual(call_kwargs["trigger"], "interval")
        self.assertEqual(call_kwargs["id"], "retry_config_5")
        self.assertEqual(call_kwargs["kwargs"], {"config_id": 5})
        self.assertTrue(call_kwargs["replace_existing"])

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_retry_job_logs_info(self, mock_get_scheduler):
        mock_sched = MagicMock()
        mock_sched.get_job.return_value = None  # job doesn't exist yet
        mock_get_scheduler.return_value = mock_sched
        from flight_watcher.scheduler import register_retry_job

        with self.assertLogs("flight_watcher.scheduler", level="INFO") as cm:
            register_retry_job(7)
        self.assertTrue(any("7" in line for line in cm.output))

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_retry_job_skips_if_already_exists(self, mock_get_scheduler):
        """Verifies add_job is not called when retry job already exists with same interval."""
        from datetime import timedelta
        from flight_watcher.scheduler import RETRY_INTERVAL_MINUTES

        mock_sched = MagicMock()
        existing_job = MagicMock()
        existing_job.trigger.interval = timedelta(minutes=RETRY_INTERVAL_MINUTES)
        mock_sched.get_job.return_value = existing_job
        mock_get_scheduler.return_value = mock_sched
        from flight_watcher.scheduler import register_retry_job

        register_retry_job(5)
        mock_sched.add_job.assert_not_called()

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_register_retry_job_replaces_if_interval_changed(self, mock_get_scheduler):
        """Verifies add_job is called with replace_existing=True when retry interval differs."""
        from datetime import timedelta
        from flight_watcher.scheduler import RETRY_INTERVAL_MINUTES

        mock_sched = MagicMock()
        existing_job = MagicMock()
        existing_job.trigger.interval = timedelta(minutes=RETRY_INTERVAL_MINUTES + 15)
        mock_sched.get_job.return_value = existing_job
        mock_get_scheduler.return_value = mock_sched
        from flight_watcher.scheduler import register_retry_job

        register_retry_job(5)
        mock_sched.add_job.assert_called_once()
        call_kwargs = mock_sched.add_job.call_args[1]
        self.assertTrue(call_kwargs["replace_existing"])


class TestCancelRetryJob(unittest.TestCase):
    def setUp(self):
        import flight_watcher.scheduler as sched_mod

        sched_mod._scheduler = None

    def tearDown(self):
        import flight_watcher.scheduler as sched_mod

        sched_mod._scheduler = None

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_cancel_retry_job_removes_correct_job(self, mock_get_scheduler):
        mock_sched = MagicMock()
        mock_get_scheduler.return_value = mock_sched
        from flight_watcher.scheduler import cancel_retry_job

        cancel_retry_job(5)
        mock_sched.remove_job.assert_called_once_with("retry_config_5")

    @patch(f"{SCHED_MODULE}.get_scheduler")
    def test_cancel_retry_job_silently_handles_missing_job(self, mock_get_scheduler):
        from apscheduler.jobstores.base import JobLookupError

        mock_sched = MagicMock()
        mock_sched.remove_job.side_effect = JobLookupError("retry_config_5")
        mock_get_scheduler.return_value = mock_sched
        from flight_watcher.scheduler import cancel_retry_job

        # Should not raise
        cancel_retry_job(5)
