import asyncio
import random
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from safer_scraper import get_carrier_by_dot
from sms_scraper import download_sms_inspection_excel
from excel_parser import parse_inspections, parse_crashes
from li_scraper import get_li_data
from geocoder import geocode_address

app = FastAPI(title="FMCSA Tool API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# State centroids — used as fallback lat/lng per inspection when no exact coords available
STATE_COORDS = {
    "AL":(32.806671,-86.791130),"AK":(61.370716,-152.404419),
    "AZ":(33.729759,-111.431221),"AR":(34.969704,-92.373123),
    "CA":(36.116203,-119.681564),"CO":(39.059811,-105.311104),
    "CT":(41.597782,-72.755371),"DE":(39.318523,-75.507141),
    "FL":(27.766279,-81.686783),"GA":(33.040619,-83.643074),
    "HI":(21.094318,-157.498337),"ID":(44.240459,-114.478828),
    "IL":(40.349457,-88.986137),"IN":(39.849426,-86.258278),
    "IA":(42.011539,-93.210526),"KS":(38.526600,-96.726486),
    "KY":(37.668140,-84.670067),"LA":(31.169960,-91.867805),
    "ME":(44.693947,-69.381927),"MD":(39.063946,-76.802101),
    "MA":(42.230171,-71.530106),"MI":(43.326618,-84.536095),
    "MN":(45.694454,-93.900192),"MS":(32.741646,-89.678696),
    "MO":(38.456085,-92.288368),"MT":(46.921925,-110.454353),
    "NE":(41.125370,-98.268082),"NV":(38.313515,-117.055374),
    "NH":(43.452492,-71.563896),"NJ":(40.298904,-74.521011),
    "NM":(34.840515,-106.248482),"NY":(42.165726,-74.948051),
    "NC":(35.630066,-79.806419),"ND":(47.528912,-99.784012),
    "OH":(40.388783,-82.764915),"OK":(35.565342,-96.928917),
    "OR":(44.572021,-122.070938),"PA":(40.590752,-77.209755),
    "RI":(41.680893,-71.511780),"SC":(33.856892,-80.945007),
    "SD":(44.299782,-99.438828),"TN":(35.747845,-86.692345),
    "TX":(31.054487,-97.563461),"UT":(40.150032,-111.862434),
    "VT":(44.045876,-72.710686),"VA":(37.769337,-78.169968),
    "WA":(47.400902,-121.490494),"WV":(38.491226,-80.954453),
    "WI":(44.268543,-89.616508),"WY":(42.755966,-107.302490),
    "DC":(38.897438,-77.026817),
}

# Jitter radius in degrees (~30 miles) so same-state inspections spread out
JITTER = 0.35


def build_inspection_points(inspections: list[dict]) -> list[dict]:
    """
    Build one map point per inspection with individual lat/lng.
    Uses state centroid + small random jitter so overlapping points
    in the same state are visually distinguishable.
    Seed jitter by report_number for determinism across reloads.
    """
    points = []
    for insp in inspections:
        state = insp.get("state", "").upper().strip()
        if not state or state not in STATE_COORDS:
            continue
        base_lat, base_lng = STATE_COORDS[state]
        report = insp.get("report_number", "")
        # Deterministic jitter seeded by report number
        rng = random.Random(hash(report) if report else id(insp))
        lat = base_lat + rng.uniform(-JITTER, JITTER)
        lng = base_lng + rng.uniform(-JITTER, JITTER)
        points.append({
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "state": state,
            "report_number": report,
            "inspection_date": insp.get("inspection_date", ""),
            "level": insp.get("level", ""),
            "basic": insp.get("basic", ""),
            "violation_description": insp.get("violation_description", ""),
            "out_of_service": insp.get("out_of_service", ""),
        })
    return points


# Also keep statewide summary for the bubble-size legend
def build_state_summary(inspections: list[dict]) -> list[dict]:
    from collections import defaultdict
    state_counts = defaultdict(lambda: {"count": 0, "oos_count": 0})
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
            "state": state, "lat": lat, "lng": lng,
            "count": data["count"], "oos_count": data["oos_count"],
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
        return {
            "status": "ok",
            "dot_number": dot_number,
            "inspections": inspections,
            "crashes": crashes,
            "inspection_points": build_inspection_points(inspections),
            "inspection_map": build_state_summary(inspections),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/li/{dot_number}")
async def get_li(dot_number: str):
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

    # Geocode carrier home address
    home_location = None
    try:
        address = carrier.get("physical_address", "")
        if address:
            coords = await geocode_address(address)
            if coords:
                home_location = {
                    "lat": coords[0],
                    "lng": coords[1],
                    "address": address,
                    "label": carrier.get("legal_name", "Carrier Home"),
                }
    except Exception as e:
        print(f"[Geocoder] Home geocoding failed: {e}")

    try:
        excel_path = await download_sms_inspection_excel(dot_number)
        inspections = parse_inspections(excel_path)
        crashes = parse_crashes(excel_path)
        inspection_points = build_inspection_points(inspections)
        inspection_map = build_state_summary(inspections)
    except Exception as e:
        inspections, crashes, inspection_points, inspection_map = [], [], [], []
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
        "home_location": home_location,
        "inspections": inspections,
        "crashes": crashes,
        "inspection_points": inspection_points,
        "inspection_map": inspection_map,
        "insurance_history": insurance_history,
        "authority_history": authority_history,
        "warnings": warnings,
    }