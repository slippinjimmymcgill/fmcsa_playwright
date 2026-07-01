"""
Scrapes the public FMCSA SAFER Company Snapshot page using Playwright.

NOTE: A plain httpx/requests GET gets a 403 Forbidden from SAFER - it appears
to block non-browser clients (likely via TLS fingerprint / header checks).
Using a real Chromium browser via Playwright gets past this.
"""

import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SAFER_SNAPSHOT_URL = (
    "https://safer.fmcsa.dot.gov/query.asp"
    "?searchtype=ANY&query_type=queryCarrierSnapshot&query_param=USDOT&query_string={dot}"
)


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def _get_value_after_label(soup: BeautifulSoup, label_text: str) -> str:
    for td in soup.find_all("td"):
        if label_text.lower() in td.get_text().lower():
            nxt = td.find_next_sibling("td")
            if nxt:
                return _clean(nxt.get_text(separator=" "))
    return ""


async def get_carrier_by_dot(dot_number: str, headless: bool = True) -> dict:
    """
    Fetch and parse the SAFER Company Snapshot page for a given USDOT number
    using a real browser session (Playwright) to avoid the 403 block that
    plain HTTP clients get.
    """
    url = SAFER_SNAPSHOT_URL.format(dot=dot_number)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        print(f"[Playwright] Loading SAFER snapshot: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text()

    if "record not found" in page_text.lower() or "no records" in page_text.lower():
        raise ValueError(f"No carrier found for USDOT {dot_number}")

    carrier = {
        "dot_number": dot_number,
        "legal_name": _get_value_after_label(soup, "Legal Name:"),
        "dba_name": _get_value_after_label(soup, "DBA Name:"),
        "usdot_status": _get_value_after_label(soup, "USDOT Status:"),
        "operating_authority_status": _get_value_after_label(soup, "Operating Authority Status:"),
        "physical_address": _get_value_after_label(soup, "Physical Address:"),
        "mailing_address": _get_value_after_label(soup, "Mailing Address:"),
        "phone": _get_value_after_label(soup, "Phone:"),
        "power_units": _get_value_after_label(soup, "Power Units:"),
        "drivers": _get_value_after_label(soup, "Drivers:"),
        "mcs150_form_date": _get_value_after_label(soup, "MCS-150 Form Date:"),
        "mc_mx_ff_numbers": _get_value_after_label(soup, "MC/MX/FF Number"),
    }

    if not carrier["legal_name"]:
        raise ValueError(
            f"Could not parse carrier data for USDOT {dot_number} - "
            "page layout may have changed, or page didn't fully load"
        )

    return carrier