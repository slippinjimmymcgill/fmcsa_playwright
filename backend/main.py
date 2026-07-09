import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from safer_scraper import get_carrier_by_dot
from sms_scraper import download_sms_inspection_excel
from excel_parser import parse_inspections, parse_crashes
from li_scraper import get_li_data

app = FastAPI(title="FMCSA Tool API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static state centroids for map plotting
STATE_COORDS = {
    "AL": (32.806671, -86.791130), "AK": (61.370716, -152.404419),
    "AZ": (33.729759, -111.431221), "AR": (34.969704, -92.373123),
    "CA": (36.116203, -119.681564), "CO": (39.059811, -105.311104),
    "CT": (41.597782, -72.755371), "DE": (39.318523, -75.507141),
    "FL": (27.766279, -81.686783), "GA": (33.040619, -83.643074),
    "HI": (21.094318, -157.498337), "ID": (44.240459, -114.478828),
    "IL": (40.349457, -88.986137), "IN": (39.849426, -86.258278),
    "IA": (42.011539, -93.210526), "KS": (38.526600, -96.726486),
    "KY": (37.668140, -84.670067), "LA": (31.169960, -91.867805),
    "ME": (44.693947, -69.381927), "MD": (39.063946, -76.802101),
    "MA": (42.230171, -71.530106), "MI": (43.326618, -84.536095),
    "MN": (45.694454, -93.900192), "MS": (32.741646, -89.678696),
    "MO": (38.456085, -92.288368), "MT": (46.921925, -110.454353),
    "NE": (41.125370, -98.268082), "NV": (38.313515, -117.055374),
    "NH": (43.452492, -71.563896), "NJ": (40.298904, -74.521011),
    "NM": (34.840515, -106.248482), "NY": (42.165726, -74.948051),
    "NC": (35.630066, -79.806419), "ND": (47.528912, -99.784012),
    "OH": (40.388783, -82.764915), "OK": (35.565342, -96.928917),
    "OR": (44.572021, -122.070938), "PA": (40.590752, -77.209755),
    "RI": (41.680893, -71.511780), "SC": (33.856892, -80.945007),
    "SD": (44.299782, -99.438828), "TN": (35.747845, -86.692345),
    "TX": (31.054487, -97.563461), "UT": (40.150032, -111.862434),
    "VT": (44.045876, -72.710686), "VA": (37.769337, -78.169968),
    "WA": (47.400902, -121.490494), "WV": (38.491226, -80.954453),
    "WI": (44.268543, -89.616508), "WY": (42.755966, -107.302490),
    "DC": (38.897438, -77.026817),
}


def build_inspection_map_data(inspections: list[dict]) -> list[dict]:
    """
    Aggregate inspections by state and attach lat/lng for map display.
    """
    from collections import defaultdict
    state_counts = defaultdict(lambda: {"count": 0, "oos_count": 0, "states": set()})

    for insp in inspections:
        state = insp.get("state", "").upper().strip()
        if not state or state not in STATE_COORDS:
            continue
        state_counts[state]["count"] += 1
        if insp.get("out_of_service", "").lower() == "yes":
            state_counts[state]["oos_count"] += 1

    result = []
    for state, data in state_counts.items():
        lat, lng = STATE_COORDS[state]
        result.append({
            "state": state,
            "lat": lat,
            "lng": lng,
            "count": data["count"],
            "oos_count": data["oos_count"],
        })
    return result


@app.get("/carrier/{dot_number}")
async def get_carrier(dot_number: str):
    try:
        carrier = await get_carrier_by_dot(dot_number)
        return {"status": "ok", "carrier": carrier}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/inspections/{dot_number}")
async def get_inspections(dot_number: str):
    try:
        file_path = await download_sms_inspection_excel(dot_number)
        inspections = parse_inspections(file_path)
        crashes = parse_crashes(file_path)
        map_data = build_inspection_map_data(inspections)
        return {
            "status": "ok",
            "dot_number": dot_number,
            "inspections": inspections,
            "crashes": crashes,
            "inspection_map": map_data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/li/{dot_number}")
async def get_li(dot_number: str):
    """Fetch Insurance History and Authority History from L&I site."""
    try:
        data = await get_li_data(dot_number)
        return {"status": "ok", **data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/full/{dot_number}")
async def get_full(dot_number: str):
    """Combined: carrier + inspections + crashes + insurance + authority + map."""
    try:
        carrier = await get_carrier_by_dot(dot_number)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    warnings = []

    try:
        excel_path = await download_sms_inspection_excel(dot_number)
        inspections = parse_inspections(excel_path)
        crashes = parse_crashes(excel_path)
        map_data = build_inspection_map_data(inspections)
    except Exception as e:
        inspections, crashes, map_data = [], [], []
        warnings.append(f"SMS download failed: {e}")

    try:
        li_data = await get_li_data(dot_number)
        insurance_history = li_data.get("insurance_history", [])
        authority_history = li_data.get("authority_history", [])
    except Exception as e:
        insurance_history, authority_history = [], []
        warnings.append(f"L&I data fetch failed: {e}")

    return {
        "status": "partial" if warnings else "ok",
        "carrier": carrier,
        "inspections": inspections,
        "crashes": crashes,
        "inspection_map": map_data,
        "insurance_history": insurance_history,
        "authority_history": authority_history,
        "warnings": warnings,
    }


@app.get("/debug-excel/{dot_number}")
async def debug_excel(dot_number: str):
    import pandas as pd, os
    file_path = os.path.join(os.path.dirname(__file__), "..", "downloads", f"sms_{dot_number}.xlsx")
    if not os.path.exists(file_path):
        return {"error": f"No file found. Run /inspections/{dot_number} first."}
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    result = {}
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, nrows=3)
        result[sheet] = {"columns": list(df.columns), "sample_rows": df.fillna("").to_dict(orient="records")}
    return {"sheets": result}

@app.get("/debug-li/{dot_number}")
async def debug_li(dot_number: str):
    """Debug L&I navigation - shows all links and table headings found on carrier 
    detail page"""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    LI_SEARCH_URL = "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrquery.prc_carrlist"

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
        await page.goto(LI_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # click through disclaimer if needed
        if await page.locator("input[name='pn_dotno']").count() == 0:
            for sel in ["input[type='submit']", "a:has-text('Carrier Search')", "a:has-text('Continue')"]:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2000)
                    break

        await page.fill("input[name='pn_dotno']", dot_number)
        await page.wait_for_timeout(500)
        await page.click("input[type='submit'][value='Search']")
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        html_link = page.locator("a:has-text('HTML')").first
        if await html_link.count() == 0:
            await browser.close()
            return {"error": "No HTML link found on search results page."}
          
        await html_link.click()
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        html = await page.content()
        url = page.url
        await browser.close()
    
    soup = BeautifulSoup(html, "html.parser")
    links = [{"text": a.get_text(strip=True), "href": a.get("href", "")} for a in soup.find_all("a") if a.get_text(strip=True)]
    tables = []
    for i, table in enumerate(soup.find_all("table")):
        rows = table.find_all("tr")
        if rows:
            headers = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]
            tables.append({
                "table_index": i,
                "headers": headers,
                "row_count": len(rows),
                "sample_rows": [
                    [td.get_text(strip=True) for td in r.find_all("td")] for r in rows[1:4]
                ]
            })
    
    return {"url": url, "links": links[:30], "tables": tables[:10]}

@app.get("/debug-li2/{dot_number}")
async def debug_li2(dot_number: str):
    """Simplified L&I debug - just loads the search page and returns what it sees."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
    import traceback

    LI_SEARCH_URL = "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrquery.prc_carrlist"

    try:
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

            # Step 1: load the page
            resp = await page.goto(LI_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            step1_url = page.url
            step1_status = resp.status
            step1_html = await page.content()
            step1_soup = BeautifulSoup(step1_html, "html.parser")
            step1_inputs = [
                {"name": i.get("name",""), "type": i.get("type",""), "value": i.get("value","")}
                for i in step1_soup.find_all("input")
            ]
            step1_links = [
                {"text": a.get_text(strip=True), "href": a.get("href","")}
                for a in step1_soup.find_all("a") if a.get_text(strip=True)
            ][:20]

            # Step 2: check if DOT input is already visible
            dot_input_visible = await page.locator("input[name='pn_dotno']").count() > 0

            result = {
                "step1_url": step1_url,
                "step1_status": step1_status,
                "dot_input_visible_immediately": dot_input_visible,
                "step1_inputs": step1_inputs,
                "step1_links": step1_links[:15],
            }

            # Step 3: if not visible, try clicking through
            if not dot_input_visible:
                clicked = None
                for sel in ["input[type='submit']", "input[type='button']", "a:has-text('Search')", "a:has-text('Continue')", "a:has-text('Accept')"]:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        clicked = sel
                        await btn.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(2000)
                        break
                result["clicked_selector"] = clicked
                result["step2_url"] = page.url
                result["dot_input_visible_after_click"] = await page.locator("input[name='pn_dotno']").count() > 0
                step2_html = await page.content()
                step2_soup = BeautifulSoup(step2_html, "html.parser")
                result["step2_inputs"] = [
                    {"name": i.get("name",""), "type": i.get("type",""), "value": i.get("value","")}
                    for i in step2_soup.find_all("input")
                ]

            await browser.close()
            return result

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
    

@app.get("/debug-li3/{dot_number}")
async def debug_li3(dot_number: str):
    """Shows the actual L&I carrier detail page content - links and all table headers."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
    import traceback

    LI_SEARCH_URL = "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrquery.prc_carrlist"

    try:
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
            await page.goto(LI_SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            await page.fill("input[name='n_dotno']", dot_number)
            await page.wait_for_timeout(500)
            await page.click("input[type='submit'][value='   Search   ']")
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            search_html = await page.content()
            search_soup = BeautifulSoup(search_html, "html.parser")
            search_links = [
                {"text": a.get_text(strip=True), "href": a.get("href", "")}
                for a in search_soup.find_all("a") if a.get_text(strip=True)
            ]

            # Click HTML link
            html_link = page.locator("a:has-text('HTML')").first
            if await html_link.count() == 0:
                await browser.close()
                return {
                    "error": "No HTML link on search results",
                    "search_url": page.url,
                    "search_links": search_links[:20],
                    "search_text_snippet": search_html[:2000],
                }

            await html_link.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            carrier_html = await page.content()
            carrier_url = page.url
            carrier_soup = BeautifulSoup(carrier_html, "html.parser")
            carrier_links = [
                {"text": a.get_text(strip=True), "href": a.get("href", "")}
                for a in carrier_soup.find_all("a") if a.get_text(strip=True)
            ]

            # Now click Insurance History
            ins_link = page.locator("a:has-text('Insurance History')").first
            ins_result = {}
            if await ins_link.count() > 0:
                await ins_link.click()
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1000)
                ins_html = await page.content()
                ins_soup = BeautifulSoup(ins_html, "html.parser")
                ins_tables = []
                for i, t in enumerate(ins_soup.find_all("table")):
                    rows = t.find_all("tr")
                    ins_tables.append({
                        "index": i,
                        "headers": [td.get_text(strip=True) for td in (rows[0].find_all(["th","td"]) if rows else [])],
                        "row_count": len(rows),
                        "sample": [[td.get_text(strip=True) for td in r.find_all("td")] for r in rows[1:3]],
                    })
                ins_result = {
                    "url": page.url,
                    "tables": ins_tables,
                    "page_text_snippet": ins_soup.get_text()[:1500],
                }
                await page.go_back()
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1000)

            # Click Authority History
            auth_link = page.locator("a:has-text('Authority History')").first
            auth_result = {}
            if await auth_link.count() > 0:
                await auth_link.click()
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1000)
                auth_html = await page.content()
                auth_soup = BeautifulSoup(auth_html, "html.parser")
                auth_tables = []
                for i, t in enumerate(auth_soup.find_all("table")):
                    rows = t.find_all("tr")
                    auth_tables.append({
                        "index": i,
                        "headers": [td.get_text(strip=True) for td in (rows[0].find_all(["th","td"]) if rows else [])],
                        "row_count": len(rows),
                        "sample": [[td.get_text(strip=True) for td in r.find_all("td")] for r in rows[1:3]],
                    })
                auth_result = {
                    "url": page.url,
                    "tables": auth_tables,
                    "page_text_snippet": auth_soup.get_text()[:1500],
                }

            await browser.close()
            return {
                "carrier_url": carrier_url,
                "carrier_links": carrier_links[:25],
                "insurance_page": ins_result,
                "authority_page": auth_result,
            }

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.get("/debug-li4/{dot_number}")
async def debug_li4(dot_number: str):
    """Shows raw content of the direct L&I carrier page."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
    import traceback

    url = (
        f"https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrquery.prc_getcarrinfo"
        f"?pv_vpath=LIVIEW&pn_dotno={dot_number}"
    )

    try:
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
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            html = await page.content()
            final_url = page.url
            status = resp.status
            await browser.close()

        soup = BeautifulSoup(html, "html.parser")
        links = [
            {"text": a.get_text(strip=True), "href": a.get("href", "")}
            for a in soup.find_all("a") if a.get_text(strip=True)
        ]
        page_text = soup.get_text()[:3000]

        return {
            "status": status,
            "final_url": final_url,
            "html_length": len(html),
            "links": links,
            "page_text_snippet": page_text,
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}