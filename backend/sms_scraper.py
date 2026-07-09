"""
Uses Playwright to navigate to FMCSA SMS carrier overview page
and download the inspection Excel export.

The Download button submits a form that causes a page navigation to serve
the file - so we use route interception to capture the response body
before the navigation completes.
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

        print(f"[SMS] Navigating to: {sms_url}")
        await page.goto(sms_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)

        # Click DOWNLOADS anchor to reveal section
        anchor = page.locator("a[href='#Downloads']").first
        if await anchor.count() > 0:
            await anchor.click()
            await page.wait_for_timeout(1500)

        # Find Download button
        btn = page.locator("input[type='submit'][value='Download']").first
        if await btn.count() == 0:
            await browser.close()
            raise RuntimeError(f"No Download button found on SMS page for DOT {dot_number}")

        print(f"[SMS] Found Download button, attempting download...")

        # Strategy 1: Use route interception to capture the file before navigation
        captured_body = None

        async def intercept_route(route):
            nonlocal captured_body
            response = await route.fetch()
            content_type = response.headers.get("content-type", "")
            content_disp = response.headers.get("content-disposition", "")
            print(f"[SMS] Route: {route.request.url[:80]} | {content_type[:50]}")
            if (
                "spreadsheet" in content_type
                or "excel" in content_type
                or "octet-stream" in content_type
                or ".xlsx" in content_disp
                or ".xls" in content_disp
            ):
                captured_body = await response.body()
                print(f"[SMS] Captured file body: {len(captured_body)} bytes")
            await route.fulfill(response=response)

        await context.route("**/*", intercept_route)

        try:
            async with page.expect_download(timeout=20000) as dl_info:
                await btn.dispatch_event("click")
            dl = await dl_info.value
            await dl.save_as(file_path)
            await browser.close()
            print(f"[SMS] Downloaded via expect_download: {file_path}")
            return file_path
        except Exception:
            pass  # Fall through to other strategies

        # Strategy 2: Use captured body from route interception
        if captured_body and len(captured_body) > 100:
            with open(file_path, "wb") as f:
                f.write(captured_body)
            await browser.close()
            print(f"[SMS] Saved from route interception: {file_path} ({len(captured_body)} bytes)")
            return file_path

        # Strategy 3: Find the form action URL and POST directly via fetch API in browser
        print(f"[SMS] Trying form POST extraction...")
        form_data = await page.evaluate("""() => {
            const btn = document.querySelector('input[type="submit"][value="Download"]');
            if (!btn) return null;
            const form = btn.closest('form');
            if (!form) return null;
            const data = {};
            for (const el of form.elements) {
                if (el.name) data[el.name] = el.value;
            }
            return { action: form.action, method: form.method, data };
        }""")

        if form_data:
            print(f"[SMS] Form action: {form_data.get('action')}")
            # Execute the POST from within the page context and capture response
            result = await page.evaluate("""async (formInfo) => {
                const body = new URLSearchParams(formInfo.data);
                const resp = await fetch(formInfo.action, {
                    method: 'POST',
                    body: body,
                    credentials: 'include',
                });
                const buffer = await resp.arrayBuffer();
                const bytes = Array.from(new Uint8Array(buffer));
                return {
                    status: resp.status,
                    contentType: resp.headers.get('content-type'),
                    size: bytes.length,
                    bytes: bytes,
                };
            }""", form_data)

            if result and result.get("size", 0) > 100:
                import struct
                byte_data = bytes(result["bytes"])
                with open(file_path, "wb") as f:
                    f.write(byte_data)
                await browser.close()
                print(f"[SMS] Saved via fetch POST: {file_path} ({len(byte_data)} bytes)")
                return file_path

        await browser.close()
        raise RuntimeError(
            f"All download strategies failed for DOT {dot_number}. "
            "The SMS page may require a different approach."
        )