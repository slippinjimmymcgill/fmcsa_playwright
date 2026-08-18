"""
Market Explorer - queries the FMCSA Company Census File and Crash File.

Dataset IDs:
  az4n-8mr2 - Company Census File (4M+ carriers)
  mjz6-e4ab - FMCSA Crash File
"""

import httpx

SOCRATA_BASE = "https://data.transportation.gov/resource"
CENSUS_ID = "az4n-8mr2"
CRASH_ID  = "aayw-vxb3"
HEADERS = {"Accept": "application/json"}


async def _get(dataset_id: str, params: dict, limit: int = 50) -> list[dict]:
    url = f"{SOCRATA_BASE}/{dataset_id}.json"
    params["$limit"] = limit
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else []
            print(f"[Market] {dataset_id} {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"[Market] {dataset_id} failed: {e}")
    return []


async def search_carriers(
    query: str = "",
    state: str = "",
    status: str = "",
    carrier_operation: str = "",
    hm_ind: str = "",
    min_power_units: str = "",
    max_power_units: str = "",
    bipd_only: bool = False,
    order_by: str = "dot_number",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    clauses = []
    if query:
        q = query.strip().replace("'", "''")
        if q.isdigit():
            clauses.append(f"dot_number='{int(q)}'")
        else:
            clauses.append(f"(upper(legal_name) like upper('%{q}%') OR upper(dba_name) like upper('%{q}%'))")
    if state:
        clauses.append(f"phy_state='{state.upper()}'")
    if status:
        clauses.append(f"status_code='{status.upper()}'")
    if carrier_operation:
        clauses.append(f"carrier_operation='{carrier_operation.upper()}'")
    if hm_ind:
        clauses.append(f"hm_ind='{hm_ind.upper()}'")
    if min_power_units:
        clauses.append(f"power_units >= '{min_power_units}'")
    if max_power_units:
        clauses.append(f"power_units <= '{max_power_units}'")
    if bipd_only:
        clauses.append("bipd_file='Y'")

    where = " AND ".join(clauses) if clauses else None
    order_map = {
        "dot_number": "dot_number ASC",
        "legal_name": "legal_name ASC",
        "power_units_desc": "power_units DESC",
        "mcs150_date": "mcs150_date DESC",
    }

    params = {"$offset": offset, "$order": order_map.get(order_by, "dot_number ASC")}
    if where:
        params["$where"] = where

    rows = await _get(CENSUS_ID, params, limit=limit)

    # Count
    count_params = {"$select": "count(*) as cnt"}
    if where:
        count_params["$where"] = where
    count_rows = await _get(CENSUS_ID, count_params, limit=1)
    total = int(count_rows[0]["cnt"]) if count_rows and "cnt" in count_rows[0] else len(rows)

    carriers = []
    for r in rows:
        carriers.append({
            "dot_number":        str(r.get("dot_number", "")),
            "legal_name":        r.get("legal_name", ""),
            "dba_name":          r.get("dba_name", ""),
            "status":            r.get("status_code", ""),
            "carrier_operation": r.get("carrier_operation", ""),
            "city":              r.get("phy_city", ""),
            "state":             r.get("phy_state", ""),
            "zip":               r.get("phy_zip", ""),
            "street":            r.get("phy_street", ""),
            "phone":             r.get("phone", ""),
            "power_units":       r.get("power_units", ""),
            "total_drivers":     r.get("total_drivers", ""),
            "hm_ind":            r.get("hm_ind", ""),
            "mcs150_date":       r.get("mcs150_date", ""),
            "bipd_file":         r.get("bipd_file", ""),
            "fleetsize":         r.get("fleetsize", ""),
        })

    return {"total": total, "carriers": carriers, "offset": offset, "limit": limit}


async def search_carriers_autocomplete(query: str, limit: int = 10) -> list[dict]:
    if not query or len(query) < 1:
        return []
    q = query.strip().replace("'", "''")
    is_numeric = q.isdigit()

    if is_numeric:
        # For DOT number prefix, use a numeric range query which is index-friendly.
        # e.g. typing "357" → DOT >= 357000000 AND DOT < 358000000
        # This works because dot_number is stored as a number in the census dataset.
        prefix_len = len(q)
        low  = int(q) * (10 ** (8 - prefix_len))  # pad right with zeros
        high = low + (10 ** (8 - prefix_len))      # next prefix block
        # Also handle shorter DOT numbers (most are 7 digits)
        low7  = int(q) * (10 ** (7 - prefix_len)) if prefix_len <= 7 else None
        high7 = (low7 + (10 ** (7 - prefix_len))) if low7 is not None else None

        if low7 is not None and low7 > 0:
            where = (
                f"(dot_number >= {low} AND dot_number < {high})"
                f" OR (dot_number >= {low7} AND dot_number < {high7})"
            )
        else:
            where = f"dot_number >= {low} AND dot_number < {high}"
    else:
        # For name prefix, LIKE 'X%' on an indexed text column is fast.
        # Socrata indexes legal_name for the Company Census dataset.
        where = f"upper(legal_name) like upper('{q}%')"

    params = {
        "$where": where,
        "$select": "dot_number,legal_name,dba_name,phy_city,phy_state,status_code",
        "$order": "dot_number ASC" if is_numeric else "legal_name ASC",
    }
    rows = await _get(CENSUS_ID, params, limit=limit)

    return [
        {
            "dot_number": str(r.get("dot_number", "")),
            "legal_name": r.get("legal_name", ""),
            "dba_name":   r.get("dba_name", ""),
            "location":   f"{r.get('phy_city','')}, {r.get('phy_state','')}".strip(", "),
            "status":     r.get("status_code", ""),
        }
        for r in rows
    ]


async def get_carrier_crashes(dot_number: str, limit: int = 100) -> list[dict]:
    params = {
        "$where": f"dot_number='{dot_number}'",
        "$order": "report_date DESC",
    }
    rows = await _get(CRASH_ID, params, limit=limit)
    crashes = []
    for r in rows:
        # Convert report_date from YYYYMMDD to YYYY-MM-DD
        raw_date = r.get("report_date", "")
        if raw_date and len(raw_date) == 8:
            raw_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        crashes.append({
            "report_number":   r.get("report_number", ""),
            "date":            raw_date,
            "state":           r.get("report_state", r.get("state", "")),
            "fatalities":      r.get("fatalities", "0"),
            "injuries":        r.get("injuries", "0"),
            "tow_away":        r.get("tow_away", ""),
            "haz_mat":         r.get("hazmat_released", r.get("vehicle_hazmat_placard", "")),
            "not_preventable": r.get("federal_recordable", ""),
            "location":        r.get("location", ""),
            "city":            r.get("city", ""),
            "carrier_name":    r.get("crash_carrier_name", ""),
            "event":           r.get("crash_event_seq_id_desc", ""),
        })
    return crashes