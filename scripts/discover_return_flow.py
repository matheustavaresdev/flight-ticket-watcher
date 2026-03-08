"""
Discover LATAM flight card selectors and return BFF request pattern.
"""
import json
import time
from pathlib import Path
from patchright.sync_api import sync_playwright

ORIGIN = "FOR"
DESTINATION = "GRU"
OUTBOUND = "2026-04-12"
INBOUND = "2026-04-17"
OUTPUT_DIR = Path("output/discovery")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    responses = []

    def on_response(response):
        url = response.url
        if "bff/" in url or "air-offers" in url:
            print(f"  [NET] {response.status} {url[:120]}")
        if "bff/air-offers" in url:
            try:
                data = response.json()
                responses.append({
                    "url": url,
                    "status": response.status,
                    "data": data,
                    "timestamp": time.time(),
                })
                print(f"  [BFF] status={response.status} offers={len(data.get('content', []))}")
            except Exception as e:
                print(f"  [BFF] status={response.status} error={e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        page = browser.new_page(no_viewport=True)
        page.on("response", on_response)

        url = (
            f"https://www.latamairlines.com/br/pt/oferta-voos"
            f"?origin={ORIGIN}&destination={DESTINATION}"
            f"&outbound={OUTBOUND}T00:00:00.000Z"
            f"&inbound={INBOUND}T00:00:00.000Z"
            f"&adt=1&chd=0&inf=0&trip=RT&cabin=Economy"
            f"&redemption=false&sort=RECOMMENDED"
        )

        print(f"Navigating to: {url}")
        try:
            with page.expect_response(
                lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                timeout=30_000,
            ):
                page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Timeout waiting for outbound BFF: {e}")
            browser.close()
            return

        print(f"\nOutbound BFF captured. Waiting for page to render...")
        page.wait_for_timeout(3000)

        # Dismiss cookie consent dialog if present
        cookie_btn = page.locator('[data-testid="cookies-politics-button--button"]')
        if cookie_btn.count() > 0:
            print("Dismissing cookie consent dialog...")
            cookie_btn.click(timeout=5000)
            page.wait_for_timeout(2000)

        # Click the first flight card
        print("\n--- Step 1: Click flight card ---")
        card = page.locator('[data-testid="wrapper-card-flight-0"]')
        print(f"wrapper-card-flight-0 visible: {card.is_visible()}")
        card.click(timeout=10_000)
        print("Card clicked. Waiting for expansion...")
        page.wait_for_timeout(3000)

        page.screenshot(path=str(OUTPUT_DIR / "after-card-click.png"), full_page=True)
        print(f"Screenshot saved: after-card-click.png")

        # Dump all visible buttons after expansion
        print("\n--- Buttons visible after card click ---")
        buttons = page.locator("button:visible")
        btn_count = buttons.count()
        print(f"Total visible buttons: {btn_count}")
        for i in range(min(btn_count, 30)):
            btn = buttons.nth(i)
            text = btn.inner_text().strip().replace('\n', ' ')[:80]
            testid = btn.get_attribute("data-testid") or ""
            aria = btn.get_attribute("aria-label") or ""
            print(f"  [{i}] text='{text}' testid='{testid}' aria='{aria}'")

        # Look for new data-testid elements that appeared after expansion
        print("\n--- data-testid elements containing 'brand' or 'offer' ---")
        brand_els = page.locator("[data-testid*='brand']")
        for i in range(min(brand_els.count(), 15)):
            el = brand_els.nth(i)
            testid = el.get_attribute("data-testid")
            tag = el.evaluate("el => el.tagName")
            visible = el.is_visible()
            print(f"  [{i}] <{tag}> testid='{testid}' visible={visible}")

        # Try to click "Escolher" if found
        print("\n--- Step 2: Try selecting a fare ---")
        pre_click_count = len(responses)

        # Try get_by_role
        escolher = page.get_by_role("button", name="Escolher")
        print(f"get_by_role('button', name='Escolher'): {escolher.count()}")

        # Try text selector
        escolher_text = page.locator("text=Escolher")
        print(f"text=Escolher: {escolher_text.count()}")

        # Try by inner text
        escolher_inner = page.locator("button >> text=Escolher")
        print(f"button >> text=Escolher: {escolher_inner.count()}")

        # Click first Escolher button
        if escolher.count() > 0:
            print("\nClicking first 'Escolher' button...")
            escolher.first.click(timeout=10_000)
            print("Fare selected!")
            page.wait_for_timeout(2000)

            page.screenshot(path=str(OUTPUT_DIR / "after-escolher.png"), full_page=True)

            # Step 3: Click "Continuar" (Continue) to proceed to return flights
            print("\n--- Step 3: Click Continuar ---")
            continuar = page.get_by_role("button", name="Continuar")
            print(f"Continuar buttons: {continuar.count()}")
            if continuar.count() > 0:
                continuar.first.click(timeout=10_000)
                print("Continuar clicked! Waiting for return BFF...")
                try:
                    page.wait_for_response(
                        lambda r: "bff/air-offers/v2/offers/search" in r.url and r.status == 200,
                        timeout=60_000,
                    )
                    print("RETURN BFF CAPTURED!")
                except Exception:
                    print("No return BFF within 60s. Waiting 15s more and checking...")
                    page.wait_for_timeout(15_000)

        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUTPUT_DIR / "final.png"), full_page=True)

        # Save all captured responses
        for i, resp in enumerate(responses):
            fname = OUTPUT_DIR / f"bff-response-{i}.json"
            fname.write_text(json.dumps({
                "url": resp["url"],
                "status": resp["status"],
                "data": resp["data"],
            }, indent=2, ensure_ascii=False))
            print(f"Saved {fname}")

        browser.close()

    print(f"\n--- Summary ---")
    print(f"Total BFF responses captured: {len(responses)}")
    for i, r in enumerate(responses):
        origin_iata = "?"
        content = r["data"].get("content", [])
        if content:
            origin_iata = content[0].get("summary", {}).get("origin", {}).get("iataCode", "?")
        print(f"  [{i}] {origin_iata}->... ({len(content)} offers)")


if __name__ == "__main__":
    main()
