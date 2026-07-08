"""
Scrapes Insurance History and Authority History from the FMCSA
Licensing & Insurance public site (li-public.fmcsa.dot.gov).
"""

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

LI_SEARCH_URL = "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrquery.prc_carrlist"
LI_BASE = "https://li-public.fmcsa.dot.gov"


def _parse_table_by_heading(soup: BeautifulSoup, heading_text: str) -> list[dict]:
    for tag in soup.find_all(["h2", "h3", "h4", "b", "strong", "td", "th"]):
        if heading_text.lower() in tag.get_text().lower():
            table = tag.find_next("table")
            if not table:
                continue
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
            headers = [h for h in headers if h]
            records = []
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if not any(cells):
                    continue
                while len(cells) < len(headers):
                    cells.append("")
                records.append(dict(zip(headers, cells[:len(headers)])))
            return records
    return []


async def get_li_data(dot_number: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        print(f"[LI] Navigating to L&I search...")
        await page.goto(LI_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # L&I site shows a disclaimer/intro page first — click through if present
        current_url = page.url
        print(f"[LI] Current URL: {current_url}")

        # If we're on the intro/disclaimer page, click Continue or the search link
        if "prc_carrlist" not in current_url or await page.locator("input[name='pn_dotno']").count() == 0:
            # Try clicking a "Continue" or "I Agree" or direct nav link
            for selector in [
                "input[type='submit']",
                "a:has-text('Carrier Search')",
                "a:has-text('Continue')",
                "a:has-text('Search')",
            ]:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    await btn.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2000)
                    break

        # If still no form, navigate directly to the search URL
        if await page.locator("input[name='pn_dotno']").count() == 0:
            await page.goto(LI_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

        # Wait explicitly for the DOT number input
        try:
            await page.locator("input[name='pn_dotno']").wait_for(state="visible", timeout=15000)
        except Exception:
            await browser.close()
            print("[LI] Could not find DOT input field")
            return {"insurance_history": [], "authority_history": []}

        await page.fill("input[name='pn_dotno']", dot_number)
        await page.wait_for_timeout(500)
        await page.click("input[type='submit'][value='Search']")
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Click HTML link for the carrier
        html_link = page.locator("a:has-text('HTML')").first
        if await html_link.count() == 0:
            await browser.close()
            return {"insurance_history": [], "authority_history": []}

        await html_link.click()
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        insurance_history = []
        authority_history = []

        # Click Insurance History
        ins_link = page.locator("a:has-text('Insurance History')").first
        if await ins_link.count() > 0:
            await ins_link.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            ins_soup = BeautifulSoup(await page.content(), "html.parser")
            insurance_history = _parse_table_by_heading(ins_soup, "Insurance History")
            await page.go_back()
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

        # Click Authority History
        auth_link = page.locator("a:has-text('Authority History')").first
        if await auth_link.count() > 0:
            await auth_link.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            auth_soup = BeautifulSoup(await page.content(), "html.parser")
            authority_history = _parse_table_by_heading(auth_soup, "Authority History")

        await browser.close()

    # Normalize insurance columns
    ins_normalized = []
    for row in insurance_history:
        ins_normalized.append({
            "effective":        row.get("Effective", row.get("Eff Date", "")),
            "cancel_effective": row.get("Cancel Effective", row.get("Cancel Eff", "")),
            "insurer":          row.get("Insurance Carrier", row.get("Insurer", "")),
            "policy":           row.get("Policy/Surety Number", row.get("Policy", "")),
            "coverage":         row.get("Coverage", row.get("Type", "")),
            "cancel_method":    row.get("Cancel Method", row.get("Cancellation Method", "")),
        })

    # Normalize authority columns
    auth_normalized = []
    for row in authority_history:
        auth_normalized.append({
            "served":    row.get("Served", row.get("Date Served", "")),
            "decided":   row.get("Decided", row.get("Decision Date", "")),
            "docket":    row.get("Docket Number", row.get("Docket", "")),
            "authority": row.get("Authority", row.get("Authority Type", "")),
            "action":    row.get("Action", row.get("Grant/Deny", "")),
        })

    return {
        "insurance_history": ins_normalized,
        "authority_history": auth_normalized,
    }