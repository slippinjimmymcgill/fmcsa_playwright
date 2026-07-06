import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from safer_scraper import get_carrier_by_dot
from sms_scraper import download_sms_inspection_excel
from excel_parser import parse_inspections, parse_crashes

app = FastAPI(title="FMCSA Tool API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/carrier/{dot_number}")
async def get_carrier(dot_number: str):
    """Fetch company details by scraping the public SAFER snapshot page."""
    try:
        carrier = await get_carrier_by_dot(dot_number)
        return {"status": "ok", "carrier": carrier}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/inspections/{dot_number}")
async def get_inspections(dot_number: str):
    """Download SMS Excel (via Playwright) and return parsed inspections."""
    try:
        file_path = await download_sms_inspection_excel(dot_number)
        inspections = parse_inspections(file_path)
        crashes = parse_crashes(file_path)
        return {"status": "ok", "dot_number": dot_number, "inspections": inspections, "crashes": crashes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/full/{dot_number}")
async def get_full(dot_number: str):
    """Combined: carrier details (SAFER scrape) + inspections (SMS Playwright download)."""
    try:
        carrier = await get_carrier_by_dot(dot_number)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        excel_path = await download_sms_inspection_excel(dot_number)
        inspections = parse_inspections(excel_path)
        crashes = parse_crashes(excel_path)
    except Exception as e:
        # Carrier details still useful even if SMS download fails
        return {
            "status": "partial",
            "carrier": carrier,
            "inspections": [],
            "crashes": [],
            "warning": f"Carrier details fetched, but SMS inspection download failed: {e}",
        }

    return {
        "status": "ok",
        "carrier": carrier,
        "inspections": inspections,
        "crashes": crashes,
    }

@app.get("/debug/{dot_number}")
async def debug_html(dot_number: str):
    """Returns raw HTML from SAFER page - remove after debugging."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    url = (
        f"https://safer.fmcsa.dot.gov/query.asp"
        f"?searchtype=ANY&query_type=queryCarrierSnapshot"
        f"&query_param=USDOT&query_string={dot_number}"
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    # Return all <td> text so we can see the real labels and structure
    tds = [td.get_text(strip=True) for td in soup.find_all("td") if td.get_text(strip=True)]
    return {"url": url, "td_count": len(tds), "all_tds": tds}

@app.get("/debug2/{dot_number}")
async def debug_fields(dot_number: str):
    """Shows td index positions for MC and Rating labels specifically."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    url = (
        f"https://safer.fmcsa.dot.gov/query.asp"
        f"?searchtype=ANY&query_type=queryCarrierSnapshot"
        f"&query_param=USDOT&query_string={dot_number}"
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    all_tds = [" ".join(td.get_text(separator=" ").split()).strip() 
               for td in soup.find_all("td")]

    # Find every td that mentions MC or Rating, show it with its neighbors
    results = []
    for i, t in enumerate(all_tds):
        if any(kw in t for kw in ["MC/MX", "Rating:", "Rating Date", "MC-"]):
            results.append({
                "index": i,
                "text": t,
                "next_1": all_tds[i+1] if i+1 < len(all_tds) else None,
                "next_2": all_tds[i+2] if i+2 < len(all_tds) else None,
            })

    return {"matches": results}

@app.get("/debug-sms/{dot_number}")
async def debug_sms(dot_number: str):
    """Shows what's on the SMS page for this DOT number."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    sms_url = f"https://ai.fmcsa.dot.gov/SMS/Carrier/{dot_number}/overview.aspx"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        resp = await page.goto(sms_url, wait_until="networkidle", timeout=60000)
        status = resp.status
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # Collect all links and buttons on the page
    links = [
        {"text": a.get_text(strip=True), "href": a.get("href", "")}
        for a in soup.find_all("a")
        if a.get_text(strip=True)
    ]
    buttons = [
        {"text": b.get_text(strip=True), "type": b.get("type", ""), "value": b.get("value", "")}
        for b in soup.find_all(["button", "input"])
        if b.get_text(strip=True) or b.get("value")
    ]

    download_btns = []
    for btn in soup.find_all("input", {"value": "Download"}):
        parent = btn.parent
        grandparent = parent.parent if parent else None
        download_btns.append({
            "type": btn.get("type"),
            "value": btn.get("value"),
            "parent_tag": parent.name if parent else None,
            "parent_id": parent.get("id") if parent else None,
            "parent_style": parent.get("style") if parent else None,
            "grandparent_tag": grandparent.name if grandparent else None,
            "grandparent_id": grandparent.get("id") if grandparent else None,
            "grandparent_style": grandparent.get("style") if grandparent else None,
        })

    return {
        "status": status,
        "url": sms_url,
        "page_title": soup.title.string if soup.title else "",
        "links": links[:40],
        "buttons": buttons[:20],
    }

@app.get("/debug-excel/{dot_number}")
async def debug_excel(dot_number: str):
    """Shows sheet names and columns of the downloaded SMS Excel."""
    import pandas as pd
    import os

    file_path = os.path.join(os.path.dirname(__file__), "..", "downloads", f"sms_{dot_number}.xlsx")

    if not os.path.exists(file_path):
        return {"error": f"No downloaded file found at {file_path}. Run /inspections/{dot_number} first."}

    xl = pd.ExcelFile(file_path, engine="openpyxl")
    result = {}
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, nrows=3)
        result[sheet] = {
            "columns": list(df.columns),
            "sample_rows": df.fillna("").to_dict(orient="records"),
        }
    return {"sheets": result}

@app.get("/debug-parse/{dot_number}")
async def debug_parse(dot_number: str):
    """Shows raw parsed rows from the Inspections sheet after skiprows=1."""
    import pandas as pd
    import os

    file_path = os.path.join(os.path.dirname(__file__), "..", "downloads", f"sms_{dot_number}.xlsx")
    if not os.path.exists(file_path):
        return {"error": f"No file found. Run /inspections/{dot_number} first."}

    xl = pd.ExcelFile(file_path, engine="openpyxl")

    # Show what we get with skiprows=1
    df = pd.read_excel(file_path, sheet_name="Inspections", engine="openpyxl", skiprows=1)
    df.columns = [str(c).strip() for c in df.columns]

    return {
        "sheet_names": xl.sheet_names,
        "row_count": len(df),
        "columns": list(df.columns),
        "first_5_rows": df.head(5).fillna("").to_dict(orient="records"),
        "non_null_counts": df.notna().sum().to_dict(),
    }