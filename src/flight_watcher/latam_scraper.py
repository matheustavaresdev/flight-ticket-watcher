"""LATAM Airlines flight search via Patchright + BFF API interception."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import typer
from patchright.sync_api import sync_playwright

from flight_watcher.browser_profiles import get_random_profile
from flight_watcher.circuit_breaker import get_breaker
from flight_watcher.errors import classify_error

logger = logging.getLogger(__name__)


def _create_context(browser):
    """Create an isolated browser context with a random fingerprint profile."""
    profile = get_random_profile()
    logger.debug(
        "Browser profile: locale=%s tz=%s viewport=%dx%d",
        profile.locale,
        profile.timezone_id,
        profile.viewport_width,
        profile.viewport_height,
    )
    context = browser.new_context(
        locale=profile.locale,
        timezone_id=profile.timezone_id,
        viewport={"width": profile.viewport_width, "height": profile.viewport_height},
    )
    page = context.new_page()
    return context, page


def _build_latam_url(
    origin: str,
    destination: str,
    outbound: str,
    inbound: str | None = None,
    trip: str = "RT",
) -> str:
    url = (
        f"https://www.latamairlines.com/br/pt/oferta-voos"
        f"?origin={origin}&destination={destination}"
        f"&outbound={outbound}T00:00:00.000Z"
    )
    if inbound:
        url += f"&inbound={inbound}T00:00:00.000Z"
    url += f"&adt=1&chd=0&inf=0&trip={trip}&cabin=Economy&redemption=false&sort=RECOMMENDED"
    return url


def search_latam(
    origin: str,
    destination: str,
    outbound: str,  # YYYY-MM-DD
    inbound: str,  # YYYY-MM-DD
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
        context, page = _create_context(browser)
        page.on("response", on_response)

        url = _build_latam_url(origin, destination, outbound, inbound, trip="RT")

        try:
            try:
                with page.expect_response(
                    lambda r: (
                        "bff/air-offers/v2/offers/search" in r.url and r.status == 200
                    ),
                    timeout=30_000,
                ):
                    page.goto(url, wait_until="domcontentloaded")
            except Exception as exc:
                category = classify_error(exc)
                logger.warning(
                    "latam search failed (category=%s): %s", category.value, exc
                )
        finally:
            context.close()
        browser.close()

    elapsed = time.time() - start
    logger.info("Search completed in %.1fs", elapsed)

    if "error" in captured:
        logger.warning(
            "response error (status=%s): %s", captured.get("status"), captured["error"]
        )
        return None

    return captured.get("data")


def search_latam_oneway(
    origin: str,
    destination: str,
    outbound: str,  # YYYY-MM-DD
    headless: bool = False,
) -> dict | None:
    """
    Search one-way LATAM flights using trip=OW URL.

    Returns the parsed BFF JSON response or None if capture failed.
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
        browser = p.chromium.launch(headless=headless, channel="chrome")
        context, page = _create_context(browser)
        page.on("response", on_response)

        url = _build_latam_url(origin, destination, outbound, trip="OW")

        try:
            try:
                with page.expect_response(
                    lambda r: (
                        "bff/air-offers/v2/offers/search" in r.url and r.status == 200
                    ),
                    timeout=30_000,
                ):
                    page.goto(url, wait_until="domcontentloaded")
            except Exception as exc:
                category = classify_error(exc)
                logger.warning(
                    "latam search failed (category=%s): %s", category.value, exc
                )
        finally:
            context.close()
        browser.close()

    elapsed = time.time() - start
    logger.info("Search completed in %.1fs", elapsed)

    if "error" in captured:
        logger.warning(
            "response error (status=%s): %s", captured.get("status"), captured["error"]
        )
        return None

    return captured.get("data")


def search_latam_roundtrip(
    origin: str,
    destination: str,
    outbound: str,  # YYYY-MM-DD
    inbound: str,  # YYYY-MM-DD
    headless: bool = False,
) -> tuple[dict | None, dict | None]:
    """
    Search LATAM round-trip flights in a single browser session.

    Mirrors the real user flow: load RT search page, capture outbound BFF,
    select a flight + fare, then capture the return BFF.

    Returns (outbound_data, return_data). Either may be None if not captured.
    """
    breaker = get_breaker()
    if not breaker.allow_request():
        logger.warning(
            "Circuit breaker OPEN — skipping LATAM search %s→%s", origin, destination
        )
        return None, None

    start = time.time()
    outbound_data = None
    return_data = None
    bff_responses: list[dict] = []
    _failure_recorded = False

    def on_response(response):
        if "bff/air-offers/v2/offers/search" in response.url:
            try:
                data = response.json()
                if (
                    response.status == 200
                    and isinstance(data, dict)
                    and "content" in data
                ):
                    bff_responses.append(data)
                    logger.info("BFF captured %d offers", len(data.get("content", [])))
            except Exception as e:
                logger.warning("BFF error: %s", e)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, channel="chrome")
        context, page = _create_context(browser)
        page.on("response", on_response)

        url = _build_latam_url(origin, destination, outbound, inbound)

        # Step 1: Load RT search page and capture outbound BFF
        try:
            with page.expect_response(
                lambda r: (
                    "bff/air-offers/v2/offers/search" in r.url and r.status == 200
                ),
                timeout=30_000,
            ):
                page.goto(url, wait_until="domcontentloaded")
        except Exception as exc:
            category = classify_error(exc)
            if not _failure_recorded:
                breaker.record_failure(category)
                _failure_recorded = True
            logger.warning("latam search failed (category=%s): %s", category.value, exc)
            context.close()
            browser.close()
            elapsed = time.time() - start
            logger.debug("Search completed in %.1fs", elapsed)
            return None, None

        if bff_responses:
            outbound_data = bff_responses[0]
            breaker.record_success()
            logger.info("Outbound: %d offers", len(outbound_data.get("content", [])))

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
            page.locator('[data-testid="cabin-grouping-tabs-0"] button').first.click(
                timeout=10_000
            )
            page.wait_for_timeout(1000)
        except Exception as exc:
            category = classify_error(exc)
            if not _failure_recorded:
                breaker.record_failure(category)
                _failure_recorded = True
            logger.warning("latam search failed (category=%s): %s", category.value, exc)
            context.close()
            browser.close()
            elapsed = time.time() - start
            logger.debug("Search completed in %.1fs", elapsed)
            return outbound_data, None

        # Step 4: Select the Light fare
        try:
            page.locator('[data-testid="bundle-detail-0-flight-select"]').wait_for(
                state="visible", timeout=30_000
            )
            page.locator('[data-testid="bundle-detail-0-flight-select"]').click(
                timeout=10_000
            )
            page.wait_for_timeout(1000)
        except Exception as exc:
            category = classify_error(exc)
            if not _failure_recorded:
                breaker.record_failure(category)
                _failure_recorded = True
            logger.warning("latam search failed (category=%s): %s", category.value, exc)
            context.close()
            browser.close()
            elapsed = time.time() - start
            logger.debug("Search completed in %.1fs", elapsed)
            return outbound_data, None

        # Step 5: Click "Continuar" and wait for return BFF
        try:
            continuar = page.get_by_role("button", name="Continuar")
            with page.expect_response(
                lambda r: (
                    "bff/air-offers/v2/offers/search" in r.url and r.status == 200
                ),
                timeout=90_000,
            ):
                continuar.click(timeout=10_000)
            logger.debug("Return BFF response captured")
        except Exception as exc:
            category = classify_error(exc)
            if not _failure_recorded:
                breaker.record_failure(category)
                _failure_recorded = True
            logger.warning("latam search failed (category=%s): %s", category.value, exc)

        # The last bff_responses entry should be the return leg
        if len(bff_responses) >= 2:
            return_data = bff_responses[-1]
            logger.info("Return: %d offers", len(return_data.get("content", [])))

        context.close()
        browser.close()

    elapsed = time.time() - start
    logger.info("Search completed in %.1fs", elapsed)
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
            offer["brands"].append(
                {
                    "id": brand.get("id"),
                    "name": brand.get("brandText"),
                    "price": brand.get("price", {}).get("amount"),
                    "currency": brand.get("price", {}).get("currency"),
                    "fare_basis": brand.get("farebasis"),
                }
            )
        offers.append(offer)
    return offers


def print_offers(offers: list[dict]) -> None:
    """Print offers in a human-readable format."""
    for i, offer in enumerate(offers, 1):
        brands_str = " | ".join(
            f"{b['name']}: {b['currency']} {b['price']:.2f}"
            for b in offer["brands"]
            if b["price"] is not None
            and b["name"] is not None
            and b["currency"] is not None
        )
        stops_str = "direct" if offer["stops"] == 0 else f"{offer['stops']} stop(s)"
        typer.echo(
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
    logger.info("Response saved to %s", filename)
    return filename
