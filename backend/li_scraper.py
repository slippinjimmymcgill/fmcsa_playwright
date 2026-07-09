"""
Fetches carrier authority and insurance data from MOTUS (motus.dot.gov),
which replaced the old li-public.fmcsa.dot.gov site.

Public access (no login required):
- /customer/{dot}/account  → basic info + operating authority links

Login.gov required (not publicly accessible):
- Insurance history
- Full authority history

We scrape what's available publicly and return clear unavailability
messages for gated data.
"""

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

MOTUS_ACCOUNT_URL = "https://motus.dot.gov/customer/{dot}/account"
MOTUS_BASE = "https://motus.dot.gov"


async def get_li_data(dot_number: str) -> dict:
    account_url = MOTUS_ACCOUNT_URL.format(dot=dot_number)

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

        print(f"[MOTUS] Loading account page: {account_url}")
        await page.goto(account_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(4000)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text()

        # Extract operating authority links (these are clickable without login)
        authority_links = []
        for a in soup.find_all("a"):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if "operating-authority-detail" in href:
                authority_links.append({
                    "text": text,
                    "url": MOTUS_BASE + href if href.startswith("/") else href
                })

        # Scrape operating authority detail pages
        authority_history = []
        for auth_link in authority_links[:5]:  # limit to 5
            try:
                await page.goto(auth_link["url"], wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)
                detail_html = await page.content()
                detail_soup = BeautifulSoup(detail_html, "html.parser")
                detail_text = detail_soup.get_text()

                # Extract key fields from the detail page text
                record = {"authority": auth_link["text"], "docket": "", "served": "", "decided": "", "action": ""}

                # Parse MC number from URL or text
                import re
                mc_match = re.search(r'MC[-\s]?(\d+)', detail_text)
                if mc_match:
                    record["docket"] = f"MC-{mc_match.group(1)}"

                # Look for status/action info
                if "active" in detail_text.lower():
                    record["action"] = "Active"
                elif "revoked" in detail_text.lower():
                    record["action"] = "Revoked"
                elif "inactive" in detail_text.lower():
                    record["action"] = "Inactive"

                # Look for grant date
                date_match = re.search(r'Grant(?:ed)?\s*Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})', detail_text)
                if date_match:
                    record["decided"] = date_match.group(1)

                authority_history.append(record)
            except Exception as e:
                print(f"[MOTUS] Error fetching authority detail: {e}")
                continue

        await browser.close()

    return {
        "insurance_history": [],
        "insurance_unavailable": (
            "Insurance history is no longer publicly accessible. "
            "FMCSA moved this data to MOTUS (motus.dot.gov) which requires "
            "a Login.gov account to access insurance records."
        ),
        "authority_history": authority_history,
        "authority_source": "MOTUS (motus.dot.gov)",
    }