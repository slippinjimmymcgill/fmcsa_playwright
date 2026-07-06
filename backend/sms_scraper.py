"""
Uses Playwright to navigate directly to the FMCSA SMS carrier overview page
and click the Download button to get the inspection Excel export.
"""

import os
from playwright.async_api import async_playwright

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


async def download_sms_inspection_excel(dot_number: str, headless: bool = True) -> str:
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

        print(f"[Playwright] Navigating to SMS overview: {sms_url}")
        await page.goto(sms_url, wait_until="networkidle", timeout=60000)

        # Wait for JS to finish rendering
        await page.wait_for_timeout(3000)

        # Try clicking the DOWNLOADS anchor to expand/reveal the section
        downloads_anchor = page.locator("a[href='#Downloads']").first
        if await downloads_anchor.count() > 0:
            print(f"[Playwright] Clicking DOWNLOADS anchor to reveal section...")
            await downloads_anchor.click()
            await page.wait_for_timeout(2000)

        # Find the Download button
        download_btn = page.locator("input[type='submit'][value='Download']").first
        if await download_btn.count() == 0:
            await browser.close()
            raise RuntimeError(
                f"No Download button found on SMS page for DOT {dot_number}."
            )

        # Use dispatch_event to click even if element is hidden
        print(f"[Playwright] Dispatching click on Download button...")
        async with page.expect_download(timeout=60000) as download_info:
            await download_btn.dispatch_event("click")

        download = await download_info.value
        file_path = os.path.join(DOWNLOAD_DIR, f"sms_{dot_number}.xlsx")
        await download.save_as(file_path)
        await browser.close()

        print(f"[Playwright] Downloaded to: {file_path}")
        return file_path