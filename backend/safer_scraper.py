"""
Scrapes the public FMCSA SAFER Company Snapshot page using Playwright.
Parser is built from the actual td structure observed from the live page.

NOTE: SAFER does NOT use label/value td pairs. Instead it uses section header tds 
followed by sequential value tds. We extract by finding known section headers 
and reading the tds that follow them in order.
"""

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

SAFER_SNAPSHOT_URL = (
    "https://safer.fmcsa.dot.gov/query.asp"
    "?searchtype=ANY&query_type=queryCarrierSnapshot"
    "&query_param=USDOT&query_string={dot}"
)


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()

def _parse_carrier(soup: BeautifulSoup, dot_number: str) -> dict:
    """
    Extract carrier fields from SAFER HTML.

    The real page structure uses flat <td> cells. Key sections are identified
    by a td whose text exactly matches a known header followed by value tds.

    Observed td sequence for USDOT INFORMATION section:
    "USDOT INFORMATION"
    entity_type         <- e.g. "CARRIER/SHIPPER/BROKER"
    usdot_status        <- e.g. "ACTIVE"
    oos_date            <- e.g. "None"
    dot_number          <- e.g. "3111532"
    state_carrier_id    <- e.g. may be empty string
    mcs150_date          <- e.g. "09/03/2018"
    mcs150_mileage       <- e.g. "1 (2017)"

    OPERATING AUTHORITY INFORMATION:
    "OPERATING AUTHORITY INFORMATION"
    operationg_authority_status (may include disclaimer text, strip at *)

    MC/MX/FF Numbers appear after "MC/MX/FF Number(s):" label td:
    "MC-82962"

    COMPANY INFORMATION:
    "COMPANY INFORMATION"
    legal_name
    dba_name
    physical_address
    phone
    mailing_address
    duns_number
    power_units
    (non-cmv units cell - skip, combined with next)
    drivers
    """

    all_tds = [_clean(td.get_text(separator=" ")) for td in soup.find_all("td")]

    def idx(label: str) -> int:
        """
        Return index of first td whose text exactly matches label.
        """
        for i, t in enumerate(all_tds):
            if t == label:
                return i
        return -1
    
    def after(label: str, offset: int = 1) -> str:
        """
        Return td text at label_index + offset.
        """
        i = idx(label)
        if i == -1:
            return ""
        target = i + offset
        return all_tds[target] if target < len(all_tds) else ""
    
    # -------------------------------------------------- #
    # USDOT INFORMATION section
    # -------------------------------------------------- #
    usdot_i = idx("USDOT INFORMATION")
    entity_type = all_tds[usdot_i + 1] if usdot_i != -1 else ""
    usdot_status = all_tds[usdot_i + 2] if usdot_i != -1 else ""
    oos_date = all_tds[usdot_i + 3] if usdot_i != -1 else ""
    mcs150_date = all_tds[usdot_i + 6] if usdot_i != -1 else ""
    mcs150_mil = all_tds[usdot_i + 7] if usdot_i != -1 else ""

    # -------------------------------------------------- #
    # OPERATING AUTHORITY INFORMATION
    # -------------------------------------------------- #
    op_auth_i = idx("OPERATING AUTHORITY INFORMATION")
    op_auth_raw = all_tds[op_auth_i + 1] if op_auth_i != -1 else ""
    # strip disclaimer that starts with "*Please Note:"
    op_auth_status = op_auth_raw.split("*Please Note:")[0].strip()

    # -------------------------------------------------- #
    # MC/MX/FF Numbers - the td immediately after "MC/MX/FF Number(s):" label
    # -------------------------------------------------- #
    mc_number = ""
    for i, t in enumerate(all_tds):
        # Match only the short standalone label td, not the long explanatory block
        if t.strip() == "MC/MX/FF Number(s):" or t.strip() == "MC/MX/FF Number(s)":
            if i + 1 < len(all_tds):
                mc_number = all_tds[i + 1].strip()
            break

    # -------------------------------------------------- #
    # COMPANY INFORMATION section
    # -------------------------------------------------- #
    co_i = idx("COMPANY INFORMATION")
    legal_name = all_tds[co_i + 1] if co_i != -1 else ""
    dba_name = all_tds[co_i + 2] if co_i != -1 else ""
    physical_address = all_tds[co_i + 3] if co_i != -1 else ""
    phone = all_tds[co_i + 4] if co_i != -1 else ""
    mailing_address = all_tds[co_i + 5] if co_i != -1 else ""
    duns_number = all_tds[co_i + 6] if co_i != -1 else ""
    power_units = all_tds[co_i + 7] if co_i != -1 else ""

    # Drivers: the td after power_units has text like "Non-CMV Units:Drivers:4"
    # Parse out the number after the last colon
    non_cmv_drivers_cell = all_tds[co_i + 8] if co_i != -1 else ""
    drivers = ""
    if "Drivers:" in non_cmv_drivers_cell:
        drivers = non_cmv_drivers_cell.split("Drivers:")[-1].strip()
    else:
        # fallback: next td is drivers directly
        drivers = all_tds[co_i + 9] if co_i != -1 and co_i + 9 < len(all_tds) else ""
    
    # -------------------------------------------------- #
    # Safety Rating - comes after "Carrier Safety Rating:" section
    # Look for the td after "Rating:" which may contain "None" or a real rating
    # -------------------------------------------------- #
    safety_rating = ""
    for i, t in enumerate(all_tds):
        if t.strip() == "Rating:":
            safety_rating = all_tds[i + 1] if i + 1 < len(all_tds) else ""
            break
    
    if not legal_name:
        raise ValueError(
            f"Could not parse carrier data for USDOT {dot_number} - "
            "SAFER page structure may have changed"
        )
    
    return {
        "dot_number": dot_number,
        "entity_type": entity_type,
        "usdot_status": usdot_status,
        "out_of_service_date": oos_date,
        "mcs150_form_date": mcs150_date,
        "mcs150_mileage_year": mcs150_mil,
        "operating_authority_status": op_auth_status,
        "mc_mx_ff_numbers": mc_number,
        "legal_name": legal_name,
        "dba_name": dba_name,
        "physical_address": physical_address,
        "phone": phone,
        "mailing_address": mailing_address,
        "duns_number": duns_number,
        "power_units": power_units,
        "drivers": drivers,
        "safety_rating": safety_rating,
    }

async def get_carrier_by_dot(dot_number: str, headless: bool = True) -> dict:
    url = SAFER_SNAPSHOT_URL.format(dot=dot_number)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
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
    
    return _parse_carrier(soup, dot_number)