"""Tests for circuit_breaker module."""

from unittest.mock import patch

from flight_watcher.circuit_breaker import CircuitBreaker, CircuitState, _DEFAULT_FAILURE_THRESHOLD
from flight_watcher.errors import ErrorCategory

CB_MODULE = "flight_watcher.circuit_breaker"


def _make_breaker(threshold=3, backoff_levels=(10, 20, 40)):
    """Create a breaker with short backoffs for testing."""
    return CircuitBreaker(failure_threshold=threshold, backoff_levels=backoff_levels)


def test_initial_state_is_closed():
    cb = _make_breaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_failures_below_threshold_stay_closed():
    cb = _make_breaker(threshold=3)
    cb.record_failure(ErrorCategory.BLOCKED)
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_threshold_reached_opens_circuit():
    cb = _make_breaker(threshold=3)
    for _ in range(3):
        cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_non_tripping_categories_ignored():
    cb = _make_breaker(threshold=1)
    cb.record_failure(ErrorCategory.NETWORK_ERROR)
    cb.record_failure(ErrorCategory.PAGE_ERROR)
    assert cb.state == CircuitState.CLOSED


def test_rate_limited_trips_breaker():
    cb = _make_breaker(threshold=2)
    cb.record_failure(ErrorCategory.RATE_LIMITED)
    cb.record_failure(ErrorCategory.RATE_LIMITED)
    assert cb.state == CircuitState.OPEN


def test_success_resets_failure_count():
    cb = _make_breaker(threshold=3)
    cb.record_failure(ErrorCategory.BLOCKED)
    cb.record_failure(ErrorCategory.BLOCKED)
    cb.record_success()
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.CLOSED  # only 1 consecutive failure


def test_open_transitions_to_half_open_after_backoff():
    cb = _make_breaker(threshold=1, backoff_levels=(5,))
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.OPEN

    with patch(f"{CB_MODULE}.time.monotonic", return_value=cb._opened_at + 5):
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True


def test_half_open_success_closes_circuit():
    cb = _make_breaker(threshold=1, backoff_levels=(0,))
    cb.record_failure(ErrorCategory.BLOCKED)
    # Force transition to HALF_OPEN
    with patch(f"{CB_MODULE}.time.monotonic", return_value=cb._opened_at + 1):
        _ = cb.state  # trigger transition
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb._backoff_index == 0


def test_half_open_failure_reopens_with_higher_backoff():
    cb = _make_breaker(threshold=1, backoff_levels=(10, 20, 40))
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb._backoff_index == 0

    # Transition to HALF_OPEN
    with patch(f"{CB_MODULE}.time.monotonic", return_value=cb._opened_at + 10):
        _ = cb.state
    # Probe fails
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.OPEN
    assert cb._backoff_index == 1  # escalated


def test_backoff_index_capped_at_max():
    cb = _make_breaker(threshold=1, backoff_levels=(1, 2))
    # Trip → HALF_OPEN → fail → Trip → HALF_OPEN → fail → Trip
    for i in range(5):
        cb.record_failure(ErrorCategory.BLOCKED)
        with patch(f"{CB_MODULE}.time.monotonic", return_value=cb._opened_at + 9999):
            _ = cb.state  # force HALF_OPEN
    assert cb._backoff_index == len(cb.backoff_levels) - 1


def test_get_breaker_returns_singleton():
    with patch.dict("os.environ", {"CB_FAILURE_THRESHOLD": "5"}):
        # Reset the module-level singleton
        import flight_watcher.circuit_breaker as mod
        mod._breaker = None
        b1 = mod.get_breaker()
        b2 = mod.get_breaker()
        assert b1 is b2
        assert b1.failure_threshold == 5
        mod._breaker = None  # cleanup


def test_get_breaker_invalid_threshold_falls_back_to_default():
    import flight_watcher.circuit_breaker as mod
    for bad_value in ("abc", "0", "-1", ""):
        mod._breaker = None
        with patch.dict("os.environ", {"CB_FAILURE_THRESHOLD": bad_value}):
            b = mod.get_breaker()
            assert b.failure_threshold == _DEFAULT_FAILURE_THRESHOLD, (
                f"Expected default for {bad_value!r}"
            )
        mod._breaker = None


def test_half_open_allows_only_one_probe():
    cb = _make_breaker(threshold=1, backoff_levels=(0,))
    cb.record_failure(ErrorCategory.BLOCKED)
    # Force HALF_OPEN
    with patch(f"{CB_MODULE}.time.monotonic", return_value=cb._opened_at + 1):
        _ = cb.state  # trigger transition
    assert cb.allow_request() is True   # first probe allowed
    assert cb.allow_request() is False  # second probe denied
