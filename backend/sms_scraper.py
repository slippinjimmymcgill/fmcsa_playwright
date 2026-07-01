"""
Uses Playwright to:
1. Go to the SAFER snapshot page for the USDOT number
2. Follow the "SMS Results" link (ai.fmcsa.dot.gov/sms/safer_xfr.aspx?DOT=...)
3. On the SMS carrier page, find and download the inspection Excel export
"""

import os
from playwright.async_api import async_playwright

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

SAFER_SNAPSHOT_URL = (
    "https://safer.fmcsa.dot.gov/query.asp"
    "?searchtype=ANY&query_type=queryCarrierSnapshot&query_param=USDOT&query_string={dot}"
)


async def download_sms_inspection_excel(dot_number: str, headless: bool = True) -> str:
    """
    Navigates SAFER -> SMS Results -> downloads the inspection Excel export.
    Returns the local file path of the downloaded .xlsx file.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # Step 1: Load SAFER snapshot page (this is where the real "SMS Results" link lives)
        snapshot_url = SAFER_SNAPSHOT_URL.format(dot=dot_number)
        print(f"[Playwright] Loading SAFER snapshot: {snapshot_url}")
        await page.goto(snapshot_url, wait_until="domcontentloaded", timeout=30000)

        # Step 2: Click through to SMS Results
        sms_link = page.locator("a:has-text('SMS Results')").first
        if await sms_link.count() == 0:
            await browser.close()
            raise RuntimeError(
                f"No 'SMS Results' link found on SAFER page for DOT {dot_number}. "
                "Carrier may have no SMS data, or SAFER page layout changed."
            )

        async with context.expect_page() as new_page_info:
            await sms_link.click()
        sms_page = await new_page_info.value
        await sms_page.wait_for_load_state("domcontentloaded", timeout=30000)
        print(f"[Playwright] On SMS page: {sms_page.url}")

        # Step 3: Find and click the Excel/download export link on the SMS page
        # SMS pages typically expose inspection data via an "Inspections" tab
        # and an export/download icon or link near the table.
        export_selectors = [
            "a:has-text('Excel')",
            "a[href*='.xlsx']",
            "a[href*='Export']",
            "a[title*='Excel']",
            "button:has-text('Excel')",
            "a:has-text('Download')",
        ]

        download_path = None
        for selector in export_selectors:
            locator = sms_page.locator(selector).first
            if await locator.count() > 0:
                try:
                    async with sms_page.expect_download(timeout=15000) as download_info:
                        await locator.click()
                    download = await download_info.value
                    download_path = os.path.join(DOWNLOAD_DIR, f"sms_{dot_number}.xlsx")
                    await download.save_as(download_path)
                    break
                except Exception as e:
                    print(f"[Playwright] Selector '{selector}' did not trigger a download: {e}")
                    continue

        await browser.close()

        if not download_path:
            raise RuntimeError(
                f"Could not locate/trigger the Excel export on the SMS page for DOT {dot_number}. "
                "Inspect the live page and update export_selectors in sms_scraper.py."
            )

        print(f"[Playwright] Downloaded to: {download_path}")
        return download_path