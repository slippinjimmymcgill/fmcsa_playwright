"""
Uses Playwright to navigate directly to the FMCSA SMS carrier overview page
and download the inspection Excel export.

The Download button is a form submit: we intercept response directly rather than waiting for a browser download event.
"""

import os
import asyncio
from playwright.async_api import async_playwright

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


async def download_sms_inspection_excel(dot_number: str, headless: bool = True) -> str:
    sms_url = f"https://ai.fmcsa.dot.gov/SMS/Carrier/{dot_number}/overview.aspx"
    file_path = os.path.join(DOWNLOAD_DIR, f"sms_{dot_number}.xlsx")

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

        print(f"[Playwright] Navigating to: {sms_url}")
        await page.goto(sms_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000) # Wait extra for JS rendering

        # Scroll DOWNLOADS anchor into view to ensure section is visible
        anchor = page.locator("a[href='#Downloads']").first
        if await anchor.count() > 0:
            await anchor.click()
            await page.wait_for_timeout(1500)

        # Find the Download button
        btn = page.locator("input[type='submit'][value='Download']").first
        if await btn.count() == 0:
            await browser.close()
            raise RuntimeError(f"No Download button found on SMS page for DOT {dot_number}")
        
        print(f"[SMS] Download button found, setting up response interception...")
        download_response = None # Set up response interception BEFORE clicking

        async def handle_response(response):
            nonlocal download_response
            content_type = response.headers.get("content-type", "")
            content_disp = response.headers.get("content-disposition", "")
            if (
                "spreadsheet" in content_type
                or "excel" in content_type
                or "octet-stream" in content_type
                or ".xlsx" in content_disp
                or ".xls" in content_disp
            ):
                print(f"[SMS] Intercepted file response: {content_type} | {content_disp}")
                download_response = response
        
        page.on("response", handle_response)

        # Try dispatch_event first (bypasses visibility)
        print(f"[SMS] Clicking Download button...")
        await btn.dispatch_event("click")

        # Wait up to 30s for the intercepted response
        for _ in range(30):
            await asyncio.sleep(0.5)
            if download_response is not None:
                break
            if download_response is None:
                # Fallback: try expect_download with force click
                print(f"[SMS] Response interception failed, trying expect_download...")
                try:
                    async with page.expect_download(timeout=30000) as dl_info:
                        await btn.dispatch_event("click")
                    dl = await dl_info.value
                    await dl.save_as(file_path)
                    await browser.close()
                    print(f"[SMS] Downloaded via expect_download to: {file_path}")
                    return file_path
                except Exception as e:
                    await browser.close()
                    raise RuntimeError(f"SMS download failed for DOT {dot_number}: {e}")
            
            # Save intercepted response body
            body = await download_response.body()
            with open(file_path, "wb") as f:
                f.write(body)
            
            await browser.close()
            print(f"[SMS] Saved intercepted response to: {file_path} ({len(body)} bytes)")
            return file_path