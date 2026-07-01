import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # first load SAFER homepage to see if blocked
        resp = await page.goto("https://safer.fmcsa.dot.gov/", wait_until="domcontentloaded", timeout=30000)
        print(f"HOMEPAGE STATUS: {resp.status}")
        await page.wait_for_timeout(3000)  # Wait for 3 seconds to observe the page
        await browser.close()

asyncio.run(main())