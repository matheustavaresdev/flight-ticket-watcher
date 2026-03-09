"""LATAM Airlines flight search via Patchright + BFF API interception."""

import json
import time
from datetime import datetime
from pathlib import Path
from patchright.sync_api import sync_playwright


def _build_latam_url(origin: str, destination: str, outbound: str, inbound: str) -> str:
    return (
        f"https://www.latamairlines.com/br/pt/oferta-voos"
        f"?origin={origin}&destination={destination}"
        f"&outbound={outbound}T00:00:00.000Z"
        f"&inbound={inbound}T00:00:00.000Z"
        f"&adt=1&chd=0&inf=0&trip=RT&cabin=Economy"
        f"&redemption=false&sort=RECOMMENDED"
    )


def search_latam(
    origin: str,
    destination: str,
    outbound: str,  # YYYY-MM-DD
    inbound: str,   # YYYY-MM-DD
    headless: bool = False,
) -> dict | None:
    """
    Search LATAM flights by navigating to the search results page
    and intercepting the BFF API response.

    Returns the parsed JSON response or None if capture failed.
    """
    start = time.time()
    captured = {}

    def on_response(response):
        if "bff/air-offers/v2/offers/search" in response.url:
            try:
                captured["data"] = response.json()
                captured["status"] = response.status
                captured.pop("error", None)
            except Exception as e:
                captured["error"] = str(e)
                captured["status"] = response.status

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            channel="chrome",
        )
        page = browser.new_page(no_viewport=True)
        page.on("response", on_response)

        url = _build_latam_url(origin, destination, outbound, inbound)

        try:
            with page.expect_response(
                lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                timeout=30_000,
            ):
                page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Timeout waiting for BFF response: {e}")

        browser.close()

    elapsed = time.time() - start
    print(f"Search completed in {elapsed:.1f}s")

    if "error" in captured:
        print(f"Response error: {captured['error']} (status {captured.get('status')})")
        return None

    return captured.get("data")


def search_latam_roundtrip(
    origin: str,
    destination: str,
    outbound: str,  # YYYY-MM-DD
    inbound: str,   # YYYY-MM-DD
    headless: bool = False,
) -> tuple[dict | None, dict | None]:
    """
    Search LATAM round-trip flights in a single browser session.

    Mirrors the real user flow: load RT search page, capture outbound BFF,
    select a flight + fare, then capture the return BFF.

    Returns (outbound_data, return_data). Either may be None if not captured.
    """
    start = time.time()
    outbound_data = None
    return_data = None
    bff_responses: list[dict] = []

    def on_response(response):
        if "bff/air-offers/v2/offers/search" in response.url:
            try:
                data = response.json()
                if response.status == 200 and isinstance(data, dict) and "content" in data:
                    bff_responses.append(data)
                    print(f"  [BFF] captured {len(data.get('content', []))} offers")
            except Exception as e:
                print(f"  [BFF] error: {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, channel="chrome")
        page = browser.new_page(no_viewport=True)
        page.on("response", on_response)

        url = _build_latam_url(origin, destination, outbound, inbound)

        # Step 1: Load RT search page and capture outbound BFF
        try:
            with page.expect_response(
                lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                timeout=30_000,
            ):
                page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Timeout waiting for outbound BFF: {e}")
            browser.close()
            elapsed = time.time() - start
            print(f"Search completed in {elapsed:.1f}s")
            return None, None

        if bff_responses:
            outbound_data = bff_responses[0]
            print(f"Outbound: {len(outbound_data.get('content', []))} offers")

        # Step 2: Dismiss cookie consent if present
        page.wait_for_timeout(2000)
        cookie_btn = page.locator('[data-testid="cookies-politics-button--button"]')
        if cookie_btn.count() > 0:
            try:
                cookie_btn.click(timeout=5000)
                page.wait_for_timeout(1000)
            except Exception:
                pass

        # Step 3: Expand Economy cabin section directly (cabin-grouping-tabs-0 is
        # already present on page load; clicking wrapper-card-flight-0 first blocks
        # the Economy button from being actionable)
        try:
            page.locator('[data-testid="cabin-grouping-tabs-0"] button').first.click(timeout=10_000)
            page.wait_for_timeout(1000)
        except Exception as e:
            print(f"Failed to expand Economy cabin: {e}")
            browser.close()
            elapsed = time.time() - start
            print(f"Search completed in {elapsed:.1f}s")
            return outbound_data, None

        # Step 4: Select the Light fare
        try:
            page.locator('[data-testid="bundle-detail-0-flight-select"]').wait_for(state="visible", timeout=30_000)
            page.locator('[data-testid="bundle-detail-0-flight-select"]').click(timeout=10_000)
            page.wait_for_timeout(1000)
        except Exception as e:
            print(f"Failed to select fare: {e}")
            browser.close()
            elapsed = time.time() - start
            print(f"Search completed in {elapsed:.1f}s")
            return outbound_data, None

        # Step 5: Click "Continuar" and wait for return BFF
        try:
            continuar = page.get_by_role("button", name="Continuar")
            with page.expect_response(
                lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                timeout=90_000,
            ):
                continuar.click(timeout=10_000)
            print("Return BFF captured")
        except Exception as e:
            print(f"Return flight capture failed: {e}")

        # The last bff_responses entry should be the return leg
        if len(bff_responses) >= 2:
            return_data = bff_responses[-1]
            print(f"Return: {len(return_data.get('content', []))} offers")

        browser.close()

    elapsed = time.time() - start
    print(f"Search completed in {elapsed:.1f}s")
    return outbound_data, return_data


def parse_offers(data: dict) -> list[dict]:
    """
    Extract fare class details from the BFF response.

    Returns a list of simplified offer dicts with brand/price breakdown.
    """
    offers = []
    for item in data.get("content", []):
        summary = item.get("summary", {})
        offer = {
            "flight_code": summary.get("flightCode"),
            "origin": summary.get("origin", {}).get("iataCode"),
            "destination": summary.get("destination", {}).get("iataCode"),
            "departure": summary.get("origin", {}).get("departure"),
            "arrival": summary.get("destination", {}).get("arrival"),
            "duration_min": summary.get("duration"),
            "stops": summary.get("stopOvers", 0),
            "brands": [],
        }
        for brand in summary.get("brands", []):
            offer["brands"].append({
                "id": brand.get("id"),
                "name": brand.get("brandText"),
                "price": brand.get("price", {}).get("amount"),
                "currency": brand.get("price", {}).get("currency"),
                "fare_basis": brand.get("farebasis"),
            })
        offers.append(offer)
    return offers


def print_offers(offers: list[dict]) -> None:
    """Print offers in a human-readable format."""
    for i, offer in enumerate(offers, 1):
        brands_str = " | ".join(
            f"{b['name']}: {b['currency']} {b['price']:.2f}"
            for b in offer["brands"]
            if b["price"] is not None and b["name"] is not None and b["currency"] is not None
        )
        stops_str = "direct" if offer["stops"] == 0 else f"{offer['stops']} stop(s)"
        print(
            f"{i:2d}. {offer['flight_code']}  "
            f"{offer['origin']}->{offer['destination']}  "
            f"{offer['departure']} ({offer['duration_min']}min, {stops_str})  "
            f"[{brands_str}]"
        )


def save_response(data: dict, origin: str, destination: str) -> Path:
    """Save raw JSON response to output/ directory."""
    output_dir = Path(__file__).parent.parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = output_dir / f"latam-{origin}-{destination}-{timestamp}.json"
    filename.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Response saved to {filename}")
    return filename


if __name__ == "__main__":
    # Default test route: Fortaleza -> São Paulo, round trip
    ORIGIN = "FOR"
    DESTINATION = "GRU"
    OUTBOUND = "2026-04-12"
    INBOUND = "2026-04-17"

    print(f"Searching LATAM: {ORIGIN} -> {DESTINATION}")
    print(f"  Outbound: {OUTBOUND}  Inbound: {INBOUND}")
    print()

    data = search_latam(ORIGIN, DESTINATION, OUTBOUND, INBOUND)

    if data:
        save_response(data, ORIGIN, DESTINATION)
        offers = parse_offers(data)
        print(f"\nFound {len(offers)} flights:\n")
        print_offers(offers)

        # Feasibility assessment
        print(f"\n--- Feasibility Result ---")
        print(f"Total offers: {len(offers)}")
        has_brands = any(len(o['brands']) > 0 for o in offers)
        print(f"Has fare classes (brands): {has_brands}")
        if has_brands:
            brand_ids = set()
            for o in offers:
                for b in o['brands']:
                    brand_ids.add(b['id'])
            print(f"Brand IDs found: {sorted(brand_ids)}")
            print("STATUS: GREEN - Feasibility confirmed")
        else:
            print("STATUS: YELLOW - Response captured but no brand data")
    else:
        print("\nSTATUS: RED - Failed to capture BFF response")
