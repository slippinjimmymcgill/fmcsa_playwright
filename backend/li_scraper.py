"""
Scrapes Insurance History and Authority History from the FMCSA
Licensing & Insurance public site (li-public.fmcsa.dot.gov).

The L&I site requires:
1. A search form submission with USDOT number
2. Clicking through to the carrier's detail page
3. Parsing the Insurance History and Authority History tables
"""

import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

LI_SEARCH_URL = "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrquery.prc_carrlist"


def _parse_table(soup: BeautifulSoup, heading_text: str) -> list[dict]:
    """
    Find a <table> near a heading that contains heading_text and parse it
    into a list of dicts using the first <tr> as column headers.
    """
    # Find the heading element
    heading = None
    for tag in soup.find_all(["h2", "h3", "h4", "b", "strong", "td"]):
        if heading_text.lower() in tag.get_text().lower():
            heading = tag
            break
    if not heading:
        return []

    # Find the next table after the heading
    table = heading.find_next("table")
    if not table:
        return []

    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    # First row = headers
    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    headers = [h for h in headers if h]  # remove empty

    records = []
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not any(cells):
            continue
        # Pad or trim cells to match header count
        while len(cells) < len(headers):
            cells.append("")
        record = dict(zip(headers, cells[:len(headers)]))
        records.append(record)

    return records


async def get_li_data(dot_number: str) -> dict:
    """
    Fetch Insurance History and Authority History for a carrier
    from the FMCSA L&I public site.
    Returns dict with keys: insurance_history, authority_history
    """
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

        # Fill in USDOT number
        await page.fill("input[name='pn_dotno']", dot_number)
        await page.wait_for_timeout(500)

        # Submit the form
        await page.click("input[type='submit']")
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # On results page, click the HTML link for this carrier
        html_link = page.locator("a:has-text('HTML')").first
        if await html_link.count() == 0:
            await browser.close()
            return {"insurance_history": [], "authority_history": []}

        await html_link.click()
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Now on carrier detail page — click Insurance History link
        ins_link = page.locator("a:has-text('Insurance History')").first
        auth_link = page.locator("a:has-text('Authority History')").first

        insurance_history = []
        authority_history = []

        if await ins_link.count() > 0:
            await ins_link.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            ins_html = await page.content()
            ins_soup = BeautifulSoup(ins_html, "html.parser")
            insurance_history = _parse_table(ins_soup, "Insurance History")
            await page.go_back()
            await page.wait_for_load_state("domcontentloaded", timeout=15000)

        if await auth_link.count() > 0:
            await auth_link.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            auth_html = await page.content()
            auth_soup = BeautifulSoup(auth_html, "html.parser")
            authority_history = _parse_table(auth_soup, "Authority History")

        await browser.close()

    # Normalize insurance history column names
    ins_normalized = []
    for row in insurance_history:
        ins_normalized.append({
            "effective":      row.get("Effective", row.get("Eff Date", "")),
            "cancel_effective": row.get("Cancel Effective", row.get("Cancel Eff", "")),
            "insurer":        row.get("Insurance Carrier", row.get("Insurer", "")),
            "policy":         row.get("Policy/Surety Number", row.get("Policy", "")),
            "coverage":       row.get("Coverage", row.get("Type", "")),
            "cancel_method":  row.get("Cancel Method", row.get("Cancellation Method", "")),
        })

    # Normalize authority history column names
    auth_normalized = []
    for row in authority_history:
        auth_normalized.append({
            "served":   row.get("Served", row.get("Date Served", "")),
            "decided":  row.get("Decided", row.get("Decision Date", "")),
            "docket":   row.get("Docket Number", row.get("Docket", "")),
            "authority": row.get("Authority", row.get("Authority Type", "")),
            "action":   row.get("Action", row.get("Grant/Deny", "")),
        })

    return {
        "insurance_history": ins_normalized,
        "authority_history": auth_normalized,
    }