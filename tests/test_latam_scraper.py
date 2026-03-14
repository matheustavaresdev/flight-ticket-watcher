"""Tests for latam_scraper module."""

from unittest.mock import MagicMock, patch

from flight_watcher.browser_profiles import BrowserProfile
from flight_watcher.latam_scraper import (
    _build_latam_url,
    parse_offers,
    search_latam,
    search_latam_oneway,
    search_latam_roundtrip,
)

SEARCH_MODULE = "flight_watcher.latam_scraper"

_FIXED_PROFILE = BrowserProfile(
    locale="pt-BR",
    timezone_id="America/Sao_Paulo",
    viewport_width=1920,
    viewport_height=1080,
)


def _make_bff_response(origin: str, destination: str, brand_price: float = 1000.0) -> dict:
    """Build a minimal BFF response matching the LATAM API structure."""
    return {
        "content": [
            {
                "summary": {
                    "flightCode": "LA1234",
                    "stopOvers": 0,
                    "duration": 215,
                    "origin": {
                        "iataCode": origin,
                        "departure": "2026-04-12T02:45:00",
                    },
                    "destination": {
                        "iataCode": destination,
                        "arrival": "2026-04-12T06:20:00",
                    },
                    "brands": [
                        {
                            "id": "SL",
                            "brandText": "LIGHT",
                            "farebasis": "GTQX0N1/DD05",
                            "price": {
                                "currency": "BRL",
                                "amount": brand_price,
                            },
                        }
                    ],
                }
            }
        ]
    }


def _setup_roundtrip_mocks(mock_pw, outbound_resp, return_resp=None):
    """Wire up Playwright mocks for roundtrip tests.

    Returns (mock_page, captured_on_response_callback).
    """
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_context.close = MagicMock()
    mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser

    # Capture the on_response callback so we can simulate BFF responses
    captured_cb = {}

    def fake_on(event, cb):
        captured_cb[event] = cb

    mock_page.on = fake_on

    # Mock expect_response as context manager
    # For outbound: simulate the BFF firing during goto
    outbound_ctx = MagicMock()

    def outbound_enter():
        return outbound_ctx

    def outbound_exit(exc_type, exc_val, exc_tb):
        # Simulate the outbound BFF response arriving
        if outbound_resp is not None:
            mock_resp = MagicMock()
            mock_resp.url = "https://www.latamairlines.com/bff/air-offers/v2/offers/search?foo=bar"
            mock_resp.status = 200
            mock_resp.json.return_value = outbound_resp
            captured_cb["response"](mock_resp)
        return False

    first_expect = MagicMock()
    first_expect.__enter__ = MagicMock(side_effect=outbound_enter)
    first_expect.__exit__ = MagicMock(side_effect=outbound_exit)

    # For return: simulate the BFF firing during Continuar click
    return_ctx = MagicMock()

    def return_enter():
        return return_ctx

    def return_exit(exc_type, exc_val, exc_tb):
        if return_resp is not None:
            mock_resp = MagicMock()
            mock_resp.url = "https://www.latamairlines.com/bff/air-offers/v2/offers/search?return=true"
            mock_resp.status = 200
            mock_resp.json.return_value = return_resp
            captured_cb["response"](mock_resp)
        return False

    second_expect = MagicMock()
    second_expect.__enter__ = MagicMock(side_effect=return_enter)
    second_expect.__exit__ = MagicMock(side_effect=return_exit)

    mock_page.expect_response.side_effect = [first_expect, second_expect]

    # Mock locator chain for cookie dismiss, card click, cabin expand, fare select
    mock_cookie_locator = MagicMock()
    mock_cookie_locator.count.return_value = 1

    mock_cabin_locator = MagicMock()  # cabin-grouping-tabs-0 button
    mock_fare_locator = MagicMock()

    def locator_side_effect(selector):
        if "cookies-politics" in selector:
            return mock_cookie_locator
        elif "cabin-grouping-tabs" in selector:
            return mock_cabin_locator
        elif "bundle-detail" in selector:
            return mock_fare_locator
        return MagicMock()

    mock_page.locator = MagicMock(side_effect=locator_side_effect)

    # Mock get_by_role for Continuar button
    mock_continuar = MagicMock()
    mock_page.get_by_role.return_value = mock_continuar

    return mock_page, captured_cb, mock_context


@patch(f"{SEARCH_MODULE}.get_random_profile", return_value=_FIXED_PROFILE)
@patch(f"{SEARCH_MODULE}.sync_playwright")
def test_roundtrip_captures_both_legs(mock_pw, mock_profile):
    """Happy path: both outbound and return BFF responses are captured."""
    outbound_resp = _make_bff_response("FOR", "GRU", brand_price=1000.0)
    return_resp = _make_bff_response("GRU", "FOR", brand_price=1200.0)

    mock_page, _, mock_context = _setup_roundtrip_mocks(mock_pw, outbound_resp, return_resp)

    outbound, ret = search_latam_roundtrip("FOR", "GRU", "2026-04-12", "2026-04-17")

    assert outbound is not None
    assert outbound["content"][0]["summary"]["origin"]["iataCode"] == "FOR"
    assert ret is not None
    assert ret["content"][0]["summary"]["origin"]["iataCode"] == "GRU"

    # Verify the interaction sequence (no card click — cabin button is clickable on load)
    mock_page.goto.assert_called_once()
    mock_page.locator.assert_any_call('[data-testid="cabin-grouping-tabs-0"] button')
    mock_page.locator.assert_any_call('[data-testid="bundle-detail-0-flight-select"]')
    mock_page.get_by_role.assert_called_once_with("button", name="Continuar")

    # Verify context is closed
    mock_context.close.assert_called_once()


@patch(f"{SEARCH_MODULE}.get_random_profile", return_value=_FIXED_PROFILE)
@patch(f"{SEARCH_MODULE}.sync_playwright")
def test_roundtrip_returns_none_when_outbound_times_out(mock_pw, mock_profile):
    """When outbound BFF never arrives, return (None, None)."""
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_context.close = MagicMock()
    mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
    mock_page.on = MagicMock()

    # Make expect_response raise (simulating timeout)
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock()
    mock_ctx.__exit__ = MagicMock(side_effect=Exception("Timeout"))
    mock_page.expect_response.return_value = mock_ctx

    outbound, ret = search_latam_roundtrip("FOR", "GRU", "2026-04-12", "2026-04-17")

    assert outbound is None
    assert ret is None
    mock_context.close.assert_called_once()
    mock_browser.close.assert_called_once()


@patch(f"{SEARCH_MODULE}.get_random_profile", return_value=_FIXED_PROFILE)
@patch(f"{SEARCH_MODULE}.sync_playwright")
def test_roundtrip_returns_none_return_when_cabin_click_fails(mock_pw, mock_profile):
    """When Economy cabin button click fails, return (outbound_data, None)."""
    outbound_resp = _make_bff_response("FOR", "GRU")

    mock_page, _, mock_context = _setup_roundtrip_mocks(mock_pw, outbound_resp, None)
    # Make cabin button click raise an exception
    mock_cabin = MagicMock()
    mock_cabin.first.click.side_effect = Exception("Click timeout")

    original_locator = mock_page.locator.side_effect

    def failing_cabin_locator(selector):
        if "cabin-grouping-tabs" in selector:
            return mock_cabin
        return original_locator(selector)

    mock_page.locator = MagicMock(side_effect=failing_cabin_locator)

    outbound, ret = search_latam_roundtrip("FOR", "GRU", "2026-04-12", "2026-04-17")

    assert outbound is not None
    assert ret is None
    mock_context.close.assert_called_once()


def test_roundtrip_url_has_correct_dates():
    """Verify the URL built for RT has correct outbound/inbound dates."""
    url = _build_latam_url("FOR", "MIA", "2026-06-18", "2026-07-03")

    assert "origin=FOR" in url
    assert "destination=MIA" in url
    assert "outbound=2026-06-18T00:00:00.000Z" in url
    assert "inbound=2026-07-03T00:00:00.000Z" in url
    assert "trip=RT" in url


def test_build_latam_url_oneway_has_trip_ow_and_no_inbound():
    """One-way URL must use trip=OW and omit the inbound parameter."""
    url = _build_latam_url("FOR", "MIA", "2026-03-12", trip="OW")

    assert "trip=OW" in url
    assert "inbound=" not in url
    assert "origin=FOR" in url
    assert "destination=MIA" in url
    assert "outbound=2026-03-12T00:00:00.000Z" in url


@patch(f"{SEARCH_MODULE}.get_random_profile", return_value=_FIXED_PROFILE)
@patch(f"{SEARCH_MODULE}.sync_playwright")
def test_search_latam_oneway_captures_single_bff(mock_pw, mock_profile):
    """One-way search navigates to OW page and returns the single BFF response."""
    bff_resp = _make_bff_response("FOR", "MIA", brand_price=2500.0)

    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_context.close = MagicMock()
    mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser

    captured_cb = {}

    def fake_on(event, cb):
        captured_cb[event] = cb

    mock_page.on = fake_on

    expect_ctx = MagicMock()

    def ctx_exit(exc_type, exc_val, exc_tb):
        mock_resp = MagicMock()
        mock_resp.url = "https://www.latamairlines.com/bff/air-offers/v2/offers/search"
        mock_resp.status = 200
        mock_resp.json.return_value = bff_resp
        captured_cb["response"](mock_resp)
        return False

    expect_ctx.__enter__ = MagicMock(return_value=expect_ctx)
    expect_ctx.__exit__ = MagicMock(side_effect=ctx_exit)
    mock_page.expect_response.return_value = expect_ctx

    result = search_latam_oneway("FOR", "MIA", "2026-03-12")

    assert result is not None
    assert result["content"][0]["summary"]["origin"]["iataCode"] == "FOR"
    # Confirm the navigated URL has trip=OW
    goto_url = mock_page.goto.call_args[0][0]
    assert "trip=OW" in goto_url
    assert "inbound=" not in goto_url
    mock_context.close.assert_called_once()


@patch(f"{SEARCH_MODULE}.get_breaker")
@patch(f"{SEARCH_MODULE}.get_random_profile", return_value=_FIXED_PROFILE)
@patch(f"{SEARCH_MODULE}.sync_playwright")
def test_roundtrip_records_failure_at_most_once_per_search(mock_pw, mock_profile, mock_get_breaker):
    """_failure_recorded flag prevents record_failure from being called more than once
    even if multiple exception handlers fire in a single search_latam_roundtrip call."""
    mock_breaker = MagicMock()
    mock_breaker.allow_request.return_value = True
    mock_get_breaker.return_value = mock_breaker

    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_context.close = MagicMock()
    mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
    mock_page.on = MagicMock()

    # Make the outbound expect_response context manager raise on __exit__
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
    mock_ctx.__exit__ = MagicMock(side_effect=Exception("Timeout — simulated block"))
    mock_page.expect_response.return_value = mock_ctx

    search_latam_roundtrip("FOR", "GRU", "2026-04-12", "2026-04-17")

    # Despite the exception propagating through the handler, record_failure must be
    # called exactly once (not once per except clause that could have fired).
    assert mock_breaker.record_failure.call_count == 1


@patch(f"{SEARCH_MODULE}.get_random_profile", return_value=_FIXED_PROFILE)
@patch(f"{SEARCH_MODULE}.sync_playwright")
def test_search_latam_closes_context(mock_pw, mock_profile):
    """search_latam() must call context.close() even when the BFF response arrives."""
    bff_resp = _make_bff_response("FOR", "GRU", brand_price=1000.0)

    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_context.close = MagicMock()
    mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser

    captured_cb = {}

    def fake_on(event, cb):
        captured_cb[event] = cb

    mock_page.on = fake_on

    expect_ctx = MagicMock()

    def ctx_exit(exc_type, exc_val, exc_tb):
        mock_resp = MagicMock()
        mock_resp.url = "https://www.latamairlines.com/bff/air-offers/v2/offers/search"
        mock_resp.status = 200
        mock_resp.json.return_value = bff_resp
        captured_cb["response"](mock_resp)
        return False

    expect_ctx.__enter__ = MagicMock(return_value=expect_ctx)
    expect_ctx.__exit__ = MagicMock(side_effect=ctx_exit)
    mock_page.expect_response.return_value = expect_ctx

    result = search_latam("FOR", "GRU", "2026-04-12", "2026-04-17")

    assert result is not None
    assert result["content"][0]["summary"]["origin"]["iataCode"] == "FOR"
    mock_context.close.assert_called_once()


def test_parse_offers_extracts_brands():
    data = _make_bff_response("FOR", "GRU", brand_price=1029.58)

    offers = parse_offers(data)

    assert len(offers) == 1
    offer = offers[0]
    assert offer["flight_code"] == "LA1234"
    assert offer["origin"] == "FOR"
    assert offer["destination"] == "GRU"
    assert offer["stops"] == 0
    assert offer["duration_min"] == 215
    assert len(offer["brands"]) == 1
    brand = offer["brands"][0]
    assert brand["id"] == "SL"
    assert brand["name"] == "LIGHT"
    assert brand["price"] == 1029.58
    assert brand["currency"] == "BRL"
    assert brand["fare_basis"] == "GTQX0N1/DD05"
