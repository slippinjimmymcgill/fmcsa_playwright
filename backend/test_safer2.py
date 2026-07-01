import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        resp = await page.goto("https://safer.fmcsa.dot.gov/query.asp?searchtype=ANY&query_type=queryCarrierSnapshot&query_param=USDOT&query_string=2033842", wait_until="domcontentloaded", timeout=30000)
        print(f"STATUS: {resp.status}")
        html = await page.content()
        print("LENGTH:", len(html))
        print("HTML:", html[:1500])  # Print first 1500 characters of the HTML
        await page.wait_for_timeout(5000)  # Wait for 5 seconds to observe the page
        await browser.close()

asyncio.run(main())