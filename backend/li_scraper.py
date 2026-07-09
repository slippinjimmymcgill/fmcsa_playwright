"""
Scrapes Insurance History and Authority History from FMCSA L&I site.

The search form is protected by reCAPTCHA so we bypass it entirely
by navigating directly to the carrier detail URL using the DOT number.
Direct URL pattern (no CAPTCHA, no form):
https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrquery.prc_getcarrinfo?pv_vpath=LIVIEW&pn_dotno={DOT}
"""

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

LI_BASE = "https://li-public.fmcsa.dot.gov"
LI_CARRIER_URL = (
    "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrquery.prc_getcarrinfo"
    "?pv_vpath=LIVIEW&pn_dotno={dot}"
)


def _parse_all_tables(soup: BeautifulSoup) -> list[dict]:
    """Parse every table on the page into a list of records, tagged with table index."""
    results = []
    for i, table in enumerate(soup.find_all("table")):
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
            results.append({"table_index": i, "headers": headers, "records": records})
    return results


def _find_table_by_heading(soup: BeautifulSoup, keyword: str) -> list[dict]:
    """Find the table that follows a heading containing keyword."""
    for tag in soup.find_all(["h1","h2","h3","h4","h5","b","strong","font","td","th"]):
        text = tag.get_text(strip=True).lower()
        if keyword.lower() in text and len(text) < 100:
            table = tag.find_next("table")
            if table:
                rows = table.find_all("tr")
                if len(rows) < 2:
                    continue
                headers = [th.get_text(strip=True) for th in rows[0].find_all(["th","td"])]
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
    url = LI_CARRIER_URL.format(dot=dot_number)

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

        print(f"[LI] Direct carrier URL: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        carrier_html = await page.content()
        carrier_soup = BeautifulSoup(carrier_html, "html.parser")
        carrier_text = carrier_soup.get_text().lower()

        # Check if we got a real carrier page or an error/redirect
        if "no carrier" in carrier_text or "not found" in carrier_text or len(carrier_html) < 1000:
            await browser.close()
            return {"insurance_history": [], "authority_history": []}

        # Find all links on carrier detail page
        all_links = [(a.get_text(strip=True), a.get("href",""))
                     for a in carrier_soup.find_all("a") if a.get_text(strip=True)]
        print(f"[LI] Carrier page links: {[l[0] for l in all_links[:20]]}")

        insurance_history = []
        authority_history = []

        # Look for Insurance History link
        ins_href = None
        auth_href = None
        for text, href in all_links:
            if "insurance" in text.lower() and "history" in text.lower():
                ins_href = href
            if "authority" in text.lower() and "history" in text.lower():
                auth_href = href

        if ins_href:
            ins_url = ins_href if ins_href.startswith("http") else LI_BASE + ins_href
            print(f"[LI] Insurance History URL: {ins_url}")
            await page.goto(ins_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            ins_soup = BeautifulSoup(await page.content(), "html.parser")
            insurance_history = _find_table_by_heading(ins_soup, "insurance")
            if not insurance_history:
                # Try parsing all tables and pick the most likely one
                all_tables = _parse_all_tables(ins_soup)
                for t in all_tables:
                    h = [x.lower() for x in t["headers"]]
                    if any(k in " ".join(h) for k in ["effective","insurer","policy","coverage"]):
                        insurance_history = t["records"]
                        break

        if auth_href:
            auth_url = auth_href if auth_href.startswith("http") else LI_BASE + auth_href
            print(f"[LI] Authority History URL: {auth_url}")
            await page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            auth_soup = BeautifulSoup(await page.content(), "html.parser")
            authority_history = _find_table_by_heading(auth_soup, "authority")
            if not authority_history:
                all_tables = _parse_all_tables(auth_soup)
                for t in all_tables:
                    h = [x.lower() for x in t["headers"]]
                    if any(k in " ".join(h) for k in ["served","decided","docket","action"]):
                        authority_history = t["records"]
                        break

        await browser.close()

    # Normalize insurance
    ins_normalized = []
    for row in insurance_history:
        ins_normalized.append({
            "effective":        next((row[k] for k in row if "effective" in k.lower() and "cancel" not in k.lower()), ""),
            "cancel_effective": next((row[k] for k in row if "cancel" in k.lower() and "effective" in k.lower()), ""),
            "insurer":          next((row[k] for k in row if any(w in k.lower() for w in ["insurer","carrier","company"])), ""),
            "policy":           next((row[k] for k in row if "policy" in k.lower() or "surety" in k.lower()), ""),
            "coverage":         next((row[k] for k in row if "coverage" in k.lower() or ("type" in k.lower() and "insurance" in k.lower())), ""),
            "cancel_method":    next((row[k] for k in row if "method" in k.lower()), ""),
        })

    # Normalize authority
    auth_normalized = []
    for row in authority_history:
        auth_normalized.append({
            "served":    next((row[k] for k in row if "served" in k.lower()), ""),
            "decided":   next((row[k] for k in row if "decided" in k.lower() or "decision" in k.lower()), ""),
            "docket":    next((row[k] for k in row if "docket" in k.lower()), ""),
            "authority": next((row[k] for k in row if "authority" in k.lower()), ""),
            "action":    next((row[k] for k in row if "action" in k.lower() or "grant" in k.lower()), ""),
        })

    return {
        "insurance_history": ins_normalized,
        "authority_history": auth_normalized,
    }