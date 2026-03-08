"""Tests for latam_scraper module."""

from unittest.mock import patch

from flight_watcher.latam_scraper import parse_offers, search_latam_roundtrip

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


def test_roundtrip_calls_search_latam_twice():
    outbound_resp = _make_bff_response("FOR", "GRU")
    return_resp = _make_bff_response("GRU", "FOR")

    with patch(f"{SEARCH_MODULE}.search_latam", side_effect=[outbound_resp, return_resp]) as mock_search, \
         patch(f"{SEARCH_MODULE}.time.sleep"):
        outbound, ret = search_latam_roundtrip("FOR", "GRU", "2026-04-12", "2026-04-17")

    assert mock_search.call_count == 2
    # First call: outbound (origin->destination, outbound->inbound dates)
    first_call_args = mock_search.call_args_list[0]
    assert first_call_args.args == ("FOR", "GRU", "2026-04-12", "2026-04-17")
    # Second call: return leg (swapped origin/destination and dates)
    second_call_args = mock_search.call_args_list[1]
    assert second_call_args.args == ("GRU", "FOR", "2026-04-17", "2026-04-12")

    assert outbound is outbound_resp
    assert ret is return_resp


def test_roundtrip_returns_none_when_outbound_fails():
    return_resp = _make_bff_response("GRU", "FOR")

    with patch(f"{SEARCH_MODULE}.search_latam", side_effect=[None, return_resp]), \
         patch(f"{SEARCH_MODULE}.time.sleep"):
        outbound, ret = search_latam_roundtrip("FOR", "GRU", "2026-04-12", "2026-04-17")

    assert outbound is None
    assert ret is return_resp


def test_roundtrip_returns_none_return_when_return_fails():
    outbound_resp = _make_bff_response("FOR", "GRU")

    with patch(f"{SEARCH_MODULE}.search_latam", side_effect=[outbound_resp, None]), \
         patch(f"{SEARCH_MODULE}.time.sleep"):
        outbound, ret = search_latam_roundtrip("FOR", "GRU", "2026-04-12", "2026-04-17")

    assert outbound is outbound_resp
    assert ret is None


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
