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
        return {
            "status": "ok",
            "dot_number": dot_number,
            "inspections": inspections,
            "crashes": crashes,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/li/{dot_number}")
async def get_li_data(dot_number: str):
    """Fetch Insurance and Authority History from DOT Open Data Portal."""
    try:
        data = await get_li_data(dot_number)
        return {"status": "ok", **data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/full/{dot_number}")
async def get_full(dot_number: str):
    """Combined: carrier details (SAFER) + inspections + crashes (SMS Excel)."""
    try:
        carrier = await get_carrier_by_dot(dot_number)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        excel_path = await download_sms_inspection_excel(dot_number)
        inspections = parse_inspections(excel_path)
        crashes = parse_crashes(excel_path)
    except Exception as e:
        return {
            "status": "partial",
            "carrier": carrier,
            "inspections": [],
            "crashes": [],
            "warning": f"Carrier details fetched, but SMS download failed: {e}",
        }

    return {
        "status": "ok",
        "carrier": carrier,
        "inspections": inspections,
        "crashes": crashes,
    }


@app.get("/debug-excel/{dot_number}")
async def debug_excel(dot_number: str):
    """Shows sheet names and columns of the downloaded SMS Excel. Remove after debugging."""
    import pandas as pd
    import os

    file_path = os.path.join(os.path.dirname(__file__), "..", "downloads", f"sms_{dot_number}.xlsx")
    if not os.path.exists(file_path):
        return {"error": f"No file at {file_path}. Run /inspections/{dot_number} first."}

    xl = pd.ExcelFile(file_path, engine="openpyxl")
    result = {}
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, nrows=3)
        result[sheet] = {
            "columns": list(df.columns),
            "sample_rows": df.fillna("").to_dict(orient="records"),
        }
    return {"sheets": result}


@app.get("/debug-li/{dot_number}")
async def debug_li(dot_number: str):
    """Debug L&I navigation - shows all links and table headings found on carrier detail page."""
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

        # Click through disclaimer if needed
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
            return {"error": "No HTML link found on search results page"}

        await html_link.click()
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        html = await page.content()
        url = page.url
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    links = [{"text": a.get_text(strip=True), "href": a.get("href", "")}
             for a in soup.find_all("a") if a.get_text(strip=True)]
    tables = []
    for i, table in enumerate(soup.find_all("table")):
        rows = table.find_all("tr")
        if rows:
            headers = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]
            tables.append({
                "table_index": i,
                "headers": headers,
                "row_count": len(rows),
                "sample": [
                    [td.get_text(strip=True) for td in r.find_all("td")]
                    for r in rows[1:4]
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


@app.get("/debug-li5/{dot_number}")
async def debug_li5(dot_number: str):
    """Find the real L&I carrier URL by following the link from SAFER page."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
    import traceback

    safer_url = (
        f"https://safer.fmcsa.dot.gov/query.asp"
        f"?searchtype=ANY&query_type=queryCarrierSnapshot"
        f"&query_param=USDOT&query_string={dot_number}"
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
            await page.goto(safer_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Find all links that mention L&I or insurance or licensing
            li_links = []
            for a in soup.find_all("a"):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if any(kw in (href+text).lower() for kw in
                       ["li-public", "licens", "insur", "li.fmcsa", "lview"]):
                    li_links.append({"text": text, "href": href})

            # Also get ALL links for reference
            all_links = [
                {"text": a.get_text(strip=True), "href": a.get("href", "")}
                for a in soup.find_all("a") if a.get_text(strip=True)
            ]

            # Try clicking the L&I link if found
            li_page_data = {}
            li_link_el = page.locator("a[href*='li-public'], a[href*='li.fmcsa'], a:has-text('Licensing'), a:has-text('Insurance')").first
            if await li_link_el.count() > 0:
                href = await li_link_el.get_attribute("href")
                li_page_data["clicked_href"] = href
                async with context.expect_page() as new_page_info:
                    await li_link_el.click()
                li_page = await new_page_info.value
                await li_page.wait_for_load_state("domcontentloaded", timeout=15000)
                await li_page.wait_for_timeout(1000)
                li_page_data["final_url"] = li_page.url
                li_html = await li_page.content()
                li_soup = BeautifulSoup(li_html, "html.parser")
                li_page_data["links"] = [
                    {"text": a.get_text(strip=True), "href": a.get("href", "")}
                    for a in li_soup.find_all("a") if a.get_text(strip=True)
                ]
                li_page_data["text_snippet"] = li_soup.get_text()[:2000]

            await browser.close()

            return {
                "safer_li_links": li_links,
                "all_safer_links": all_links[:30],
                "li_page": li_page_data,
            }

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/debug-li6/{dot_number}")
async def debug_li6(dot_number: str):
    """Extract L&I link href from SAFER page without clicking it."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
    import traceback

    safer_url = (
        f"https://safer.fmcsa.dot.gov/query.asp"
        f"?searchtype=ANY&query_type=queryCarrierSnapshot"
        f"&query_param=USDOT&query_string={dot_number}"
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
            await page.goto(safer_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Extract ALL links with their hrefs
            all_links = [
                {"text": a.get_text(strip=True), "href": a.get("href", "")}
                for a in soup.find_all("a") if a.get_text(strip=True)
            ]

            # Find L&I related links
            li_links = [
                l for l in all_links
                if any(kw in (l["href"] + l["text"]).lower()
                       for kw in ["li-public", "licens", "insur", "l&i", "li.fmcsa"])
            ]

            # Also look for the specific "Licensing & Insurance" text link
            lic_ins_links = [
                l for l in all_links
                if "licens" in l["text"].lower() or "insur" in l["text"].lower()
            ]

            # Now navigate directly to whatever L&I URL we find
            li_page_result = {}
            target_url = None
            for l in li_links + lic_ins_links:
                href = l["href"]
                if href and href.startswith("http"):
                    target_url = href
                    break
                elif href and href.startswith("/"):
                    target_url = "https://li-public.fmcsa.dot.gov" + href
                    break

            if target_url:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                li_html = await page.content()
                li_soup = BeautifulSoup(li_html, "html.parser")
                li_page_result = {
                    "url": page.url,
                    "status": "loaded",
                    "links": [
                        {"text": a.get_text(strip=True), "href": a.get("href", "")}
                        for a in li_soup.find_all("a") if a.get_text(strip=True)
                    ][:30],
                    "text": li_soup.get_text()[:2000],
                }

            await browser.close()
            return {
                "all_safer_links": all_links,
                "li_links_found": li_links,
                "lic_ins_links": lic_ins_links,
                "target_url": target_url,
                "li_page": li_page_result,
            }

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/debug-motus/{dot_number}")
async def debug_motus(dot_number: str):
    """Explore MOTUS sub-pages for insurance and authority history."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
    import traceback

    base_url = f"https://motus.dot.gov/customer/{dot_number}"
    sub_pages = [
        f"{base_url}/account",
        f"{base_url}/insurance",
        f"{base_url}/insurance-history",
        f"{base_url}/authority",
        f"{base_url}/authority-history",
        f"{base_url}/operating-authority",
    ]

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

            # First load the account page and wait for React to render
            await page.goto(f"{base_url}/account", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)

            # Get all navigation links visible after JS renders
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            all_links = [
                {"text": a.get_text(strip=True), "href": a.get("href", "")}
                for a in soup.find_all("a") if a.get_text(strip=True)
            ]
            full_text = soup.get_text()[:3000]

            # Try each sub-page URL
            results = {}
            for url in sub_pages:
                try:
                    resp = await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(3000)
                    sub_html = await page.content()
                    sub_soup = BeautifulSoup(sub_html, "html.parser")
                    sub_text = sub_soup.get_text()
                    results[url] = {
                        "status": resp.status,
                        "final_url": page.url,
                        "text_length": len(sub_text),
                        "text_snippet": sub_text[:1000],
                        "links": [
                            {"text": a.get_text(strip=True), "href": a.get("href", "")}
                            for a in sub_soup.find_all("a") if a.get_text(strip=True)
                        ][:20],
                    }
                except Exception as e:
                    results[url] = {"error": str(e)}

            await browser.close()
            return {
                "account_links": all_links,
                "account_text": full_text,
                "sub_pages": results,
            }

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@app.get("/debug-socrata/{dot_number}")
async def debug_socrata(dot_number: str):
    """Test all Socrata dataset IDs and show raw field names returned."""
    import httpx
    padded = dot_number.zfill(8)

    datasets = {
        "InsHist_daily_xkmg-ff2t": f"https://data.transportation.gov/resource/xkmg-ff2t.json?$where=dot_number='{padded}'&$limit=3",
        "InsHist_allhist_xkn3-5fci": f"https://data.transportation.gov/resource/xkn3-5fci.json?$where=dot_number='{padded}'&$limit=3",
        "InsHist_unpadded_xkmg": f"https://data.transportation.gov/resource/xkmg-ff2t.json?$where=dot_number='{dot_number}'&$limit=3",
        "AuthHist_9mw4": f"https://data.transportation.gov/resource/9mw4-x3tu.json?$where=dot_number='{padded}'&$limit=3",
        "InsHist_6sqe_padded": f"https://data.transportation.gov/resource/6sqe-dvqs.json?$where=dot_number='{padded}'&$limit=3",
        "InsHist_6sqe_unpadded": f"https://data.transportation.gov/resource/6sqe-dvqs.json?$where=dot_number='{dot_number}'&$limit=3",
        "MotusInsHist_rqg5": f"https://data.transportation.gov/resource/rqg5-mte8.json?$where=usdot_number='{dot_number}'&$limit=3",
        "MotusAuthHist_a37f": f"https://data.transportation.gov/resource/a37f-s6p3.json?$where=usdot_number='{dot_number}'&$limit=3",
    }

    results = {}
    async with httpx.AsyncClient(timeout=15) as client:
        for name, url in datasets.items():
            try:
                resp = await client.get(url)
                data = resp.json()
                results[name] = {
                    "status": resp.status_code,
                    "count": len(data) if isinstance(data, list) else 0,
                    "fields": list(data[0].keys()) if isinstance(data, list) and data else [],
                    "sample": data[0] if isinstance(data, list) and data else data,
                }
            except Exception as e:
                results[name] = {"error": str(e)}

    return {"padded_dot": padded, "results": results}