"""
Scrapes Insurance History and Authority History from the FMCSA
Licensing & Insurance public site (li-public.fmcsa.dot.gov).

Key finding from debug: field name is 'n_dotno' not 'pn_dotno'.
The search form is on the first page load - no disclaimer click needed.
"""

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

LI_SEARCH_URL = "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrquery.prc_carrlist"
LI_BASE = "https://li-public.fmcsa.dot.gov"


def _parse_table_by_heading(soup: BeautifulSoup, heading_text: str) -> list[dict]:
    """Find a table near a heading containing heading_text and parse into list of dicts."""
    for tag in soup.find_all(["h2", "h3", "h4", "b", "strong", "td", "th", "font"]):
        if heading_text.lower() in tag.get_text().lower():
            table = tag.find_next("table")
            if not table:
                continue
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
            headers = [h for h in headers if h]
            if not headers:
                continue
            records = []
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if not any(cells):
                    continue
                while len(cells) < len(headers):
                    cells.append("")
                records.append(dict(zip(headers, cells[:len(headers)])))
            if records:
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

        print(f"[LI] Loading search page...")
        await page.goto(LI_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Field is 'n_dotno' (confirmed from debug output)
        dot_field = page.locator("input[name='n_dotno']").first
        if await dot_field.count() == 0:
            await browser.close()
            print("[LI] Could not find n_dotno input field")
            return {"insurance_history": [], "authority_history": []}

        await page.fill("input[name='n_dotno']", dot_number)
        await page.wait_for_timeout(500)

        # Click the Search submit button
        await page.click("input[type='submit'][value='   Search   ']")
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Check for reCAPTCHA challenge
        page_text = await page.inner_text("body")
        if "captcha" in page_text.lower() or "robot" in page_text.lower():
            await browser.close()
            print("[LI] Blocked by reCAPTCHA")
            return {"insurance_history": [], "authority_history": [], "blocked_by_captcha": True}

        # Click HTML link for this carrier
        html_link = page.locator("a:has-text('HTML')").first
        if await html_link.count() == 0:
            await browser.close()
            print("[LI] No HTML link found on results page")
            return {"insurance_history": [], "authority_history": []}

        await html_link.click()
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        insurance_history = []
        authority_history = []

        # Click Insurance History link
        ins_link = page.locator("a:has-text('Insurance History')").first
        if await ins_link.count() > 0:
            await ins_link.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            ins_soup = BeautifulSoup(await page.content(), "html.parser")
            insurance_history = _parse_table_by_heading(ins_soup, "Insurance")
            await page.go_back()
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

        # Click Authority History link
        auth_link = page.locator("a:has-text('Authority History')").first
        if await auth_link.count() > 0:
            await auth_link.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            auth_soup = BeautifulSoup(await page.content(), "html.parser")
            authority_history = _parse_table_by_heading(auth_soup, "Authority")

        await browser.close()

    # Normalize insurance columns - try multiple possible header names
    ins_normalized = []
    for row in insurance_history:
        ins_normalized.append({
            "effective":        row.get("Effective", row.get("Eff Date", row.get("Effective Date", ""))),
            "cancel_effective": row.get("Cancel Effective", row.get("Cancel Eff Date", row.get("Cancellation Date", ""))),
            "insurer":          row.get("Insurance Carrier", row.get("Insurer", row.get("Company", ""))),
            "policy":           row.get("Policy/Surety Number", row.get("Policy Number", row.get("Policy", ""))),
            "coverage":         row.get("Coverage", row.get("Type of Insurance", row.get("Type", ""))),
            "cancel_method":    row.get("Cancel Method", row.get("Cancellation Method", row.get("Method", ""))),
        })

    # Normalize authority columns
    auth_normalized = []
    for row in authority_history:
        auth_normalized.append({
            "served":    row.get("Served", row.get("Date Served", row.get("Service Date", ""))),
            "decided":   row.get("Decided", row.get("Decision Date", row.get("Date Decided", ""))),
            "docket":    row.get("Docket Number", row.get("Docket No.", row.get("Docket", ""))),
            "authority": row.get("Authority", row.get("Authority Type", row.get("Type", ""))),
            "action":    row.get("Action", row.get("Grant/Deny", row.get("Decision", ""))),
        })

    return {
        "insurance_history": ins_normalized,
        "authority_history": auth_normalized,
    }