from flight_watcher.errors import (
    ErrorCategory,
    classify_error,
    get_retry_strategy,
    get_error_hint,
    ERROR_HINTS,
)


def test_classify_429_as_rate_limited():
    assert classify_error(Exception(""), status_code=429) == ErrorCategory.RATE_LIMITED


def test_classify_403_as_blocked():
    assert classify_error(Exception(""), status_code=403) == ErrorCategory.BLOCKED


def test_classify_timeout_as_network_error():
    assert (
        classify_error(Exception("Timeout 30000ms exceeded"))
        == ErrorCategory.NETWORK_ERROR
    )


def test_classify_element_not_found_as_page_error():
    assert (
        classify_error(Exception("element not found in page"))
        == ErrorCategory.PAGE_ERROR
    )


def test_classify_unknown_as_network_error():
    assert (
        classify_error(Exception("something weird happened"))
        == ErrorCategory.NETWORK_ERROR
    )


def test_retry_strategy_rate_limited_has_long_backoff():
    strategy = get_retry_strategy(ErrorCategory.RATE_LIMITED)
    assert strategy.min_delay_sec >= 1800


def test_retry_strategy_page_error_skips():
    strategy = get_retry_strategy(ErrorCategory.PAGE_ERROR)
    assert strategy.skip_item is True


def test_retry_strategy_blocked_no_retry():
    strategy = get_retry_strategy(ErrorCategory.BLOCKED)
    assert strategy.max_retries == 0
    assert strategy.skip_item is False


def test_get_error_hint_returns_hint_for_each_category():
    for category in ErrorCategory:
        hint = get_error_hint(category)
        assert isinstance(hint, str)
        assert len(hint) > 0


def test_get_error_hint_formats_context():
    hint = get_error_hint(
        ErrorCategory.NETWORK_ERROR,
        search_type="fast",
        origin="GRU",
        dest="FOR",
        date="2026-04-12",
    )
    assert "GRU" in hint
    assert "FOR" in hint
    assert "2026-04-12" in hint


def test_get_error_hint_missing_context_returns_template():
    # Call with no context — should return the raw template (with unformatted placeholders)
    hint = get_error_hint(ErrorCategory.NETWORK_ERROR)
    assert isinstance(hint, str)
    assert len(hint) > 0
    # Should contain the unformatted placeholder since no context was provided
    assert "{origin}" in hint or "origin" in hint
