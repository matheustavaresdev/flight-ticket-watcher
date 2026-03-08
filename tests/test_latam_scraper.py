"""Tests for latam_scraper module."""

from unittest.mock import MagicMock, patch, call

from flight_watcher.latam_scraper import (
    _build_latam_url,
    parse_offers,
    search_latam_roundtrip,
)

SEARCH_MODULE = "flight_watcher.latam_scraper"


def _make_bff_response(origin: str, destination: str, brand_price: float = 1000.0) -> dict:
    """Build a minimal BFF response matching the LATAM API structure."""
    return {
        "content": [
            {
                "summary": {
                    "flightCode": f"LA1234",
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
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page
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

    mock_card_locator = MagicMock()
    mock_cabin_locator = MagicMock()  # cabin-grouping-tabs-0 button
    mock_fare_locator = MagicMock()

    def locator_side_effect(selector):
        if "cookies-politics" in selector:
            return mock_cookie_locator
        elif "wrapper-card-flight" in selector:
            return mock_card_locator
        elif "cabin-grouping-tabs" in selector:
            return mock_cabin_locator
        elif "bundle-detail" in selector:
            return mock_fare_locator
        return MagicMock()

    mock_page.locator = MagicMock(side_effect=locator_side_effect)

    # Mock get_by_role for Continuar button
    mock_continuar = MagicMock()
    mock_page.get_by_role.return_value = mock_continuar

    return mock_page, captured_cb


@patch(f"{SEARCH_MODULE}.sync_playwright")
def test_roundtrip_captures_both_legs(mock_pw):
    """Happy path: both outbound and return BFF responses are captured."""
    outbound_resp = _make_bff_response("FOR", "GRU", brand_price=1000.0)
    return_resp = _make_bff_response("GRU", "FOR", brand_price=1200.0)

    mock_page, _ = _setup_roundtrip_mocks(mock_pw, outbound_resp, return_resp)

    outbound, ret = search_latam_roundtrip("FOR", "GRU", "2026-04-12", "2026-04-17")

    assert outbound is not None
    assert outbound["content"][0]["summary"]["origin"]["iataCode"] == "FOR"
    assert ret is not None
    assert ret["content"][0]["summary"]["origin"]["iataCode"] == "GRU"

    # Verify the interaction sequence
    mock_page.goto.assert_called_once()
    mock_page.locator.assert_any_call('[data-testid="wrapper-card-flight-0"]')
    mock_page.locator.assert_any_call('[data-testid="cabin-grouping-tabs-0"] button')
    mock_page.locator.assert_any_call('[data-testid="bundle-detail-0-flight-select"]')
    mock_page.get_by_role.assert_called_once_with("button", name="Continuar")


@patch(f"{SEARCH_MODULE}.sync_playwright")
def test_roundtrip_returns_none_when_outbound_times_out(mock_pw):
    """When outbound BFF never arrives, return (None, None)."""
    mock_browser = MagicMock()
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page
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
    mock_browser.close.assert_called_once()


@patch(f"{SEARCH_MODULE}.sync_playwright")
def test_roundtrip_returns_none_return_when_click_fails(mock_pw):
    """When card click fails, return (outbound_data, None)."""
    outbound_resp = _make_bff_response("FOR", "GRU")

    mock_page, _ = _setup_roundtrip_mocks(mock_pw, outbound_resp, None)
    # Make card click raise an exception
    mock_card = MagicMock()
    mock_card.click.side_effect = Exception("Click timeout")

    original_locator = mock_page.locator.side_effect

    def failing_card_locator(selector):
        if "wrapper-card-flight" in selector:
            return mock_card
        return original_locator(selector)

    mock_page.locator = MagicMock(side_effect=failing_card_locator)

    outbound, ret = search_latam_roundtrip("FOR", "GRU", "2026-04-12", "2026-04-17")

    assert outbound is not None
    assert ret is None


def test_roundtrip_url_has_correct_dates():
    """Verify the URL built for RT has correct outbound/inbound dates."""
    url = _build_latam_url("FOR", "MIA", "2026-06-18", "2026-07-03")

    assert "origin=FOR" in url
    assert "destination=MIA" in url
    assert "outbound=2026-06-18T00:00:00.000Z" in url
    assert "inbound=2026-07-03T00:00:00.000Z" in url
    assert "trip=RT" in url


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
