"""
Uses Playwright to navigate directly to the FMCSA SMS carrier overview page
and click the Download button to get the inspection Excel export.

No new-tab handling needed, the Download button triggers a file download
directly on the overview page.
"""

import os
from playwright.async_api import async_playwright

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

async def download_sms_inspection_excel(dot_number: str, headless: bool = True) -> str:
    """
    Navigates directly to the SMS carrier overview page and clicks the
    Download button to trigger the Excel export.
    Returns the local file path of the downloaded file.
    """
    sms_url = f"https://ai.fmcsa.dot.gov/SMS/Carrier/{dot_number}/overview.aspx"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        print(f"[Playwright] Navigating to SMS overview page: {sms_url}")
        await page.goto(sms_url, wait_until="networkidle", timeout=60000)

        # scroll to the Downloads section first
        downloads_anchor = page.locator("a[href='#Downloads']").first
        if await downloads_anchor.count() > 0:
            await downloads_anchor.scroll_into_view_if_needed()
            await page.wait_for_timeout(1000)  # wait a moment for any lazy loading

        # Click the "Download" submit button to trigger the Excel download
        download_btn = page.locator("input[type='submit'][value='Download']").first
        if await download_btn.count() == 0:
            await browser.close()
            raise RuntimeError(
                f"No download button found on SMS page for DOT {dot_number}. "
                f"URL: {sms_url}"
            )
        
        print(f"[Playwright] Clicking Download button...")
        async with page.expect_download(timeout=60000) as download_info:
            await download_btn.click()
        download = await download_info.value
        file_path = os.path.join(DOWNLOAD_DIR, f"sms_{dot_number}.xlsx")
        await download.save_as(file_path)
        await browser.close()
        print(f"[Playwright] Downloaded to: {file_path}")
        return file_path