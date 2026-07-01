import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from safer_scraper import get_carrier_by_dot
from sms_scraper import download_sms_inspection_excel
from excel_parser import parse_inspections

app = FastAPI(title="FMCSA Tool API (No API Key Required)")

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
        return {"status": "ok", "dot_number": dot_number, "inspections": inspections}
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
    except Exception as e:
        # Carrier details still useful even if SMS download fails
        return {
            "status": "partial",
            "carrier": carrier,
            "inspections": [],
            "warning": f"Carrier details fetched, but SMS inspection download failed: {e}",
        }

    return {
        "status": "ok",
        "carrier": carrier,
        "inspections": inspections,
    }