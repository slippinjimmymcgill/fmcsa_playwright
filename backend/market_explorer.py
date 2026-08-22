"""
Market Explorer - queries the FMCSA Company Census File and Crash File.

Dataset IDs:
  az4n-8mr2 - Company Census File (4M+ carriers)
  mjz6-e4ab - FMCSA Crash File
  6eyk-hxee - Carrier All With History (L&I). This is the ONLY dataset that
              has BIPD data -- the Company Census File has no BIPD column at
              all. dot_number on this dataset is a zero-padded 8-digit
              string (e.g. "02217388"), unlike the Census File where it's
              numeric, hence the pad/unpad helpers below.

              IMPORTANT: bipd_file is NOT a "Y"/"N" flag. It holds the filed
              coverage amount in thousands of dollars as a zero-padded
              string (e.g. "00750" = $750,000), matching min_cov_amount.
              A carrier has an active BIPD filing iff this parses to a
              number > 0. (cargo_file/bond_file on this same dataset ARE
              genuine "Y"/"N" strings -- only bipd_file is amount-encoded,
              confirmed against live data for DOT 3576562.) Treating it as
              "Y"/"N" was the actual bug: the value was being fetched
              correctly the whole time, just never matched.
"""

import httpx

SOCRATA_BASE = "https://data.transportation.gov/resource"
CENSUS_ID = "az4n-8mr2"
CRASH_ID  = "aayw-vxb3"
LI_CARRIER_ID = "6eyk-hxee"
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


def _pad_dot(dot_number: str) -> str:
    return str(dot_number).strip().zfill(8)


def _unpad_dot(padded: str) -> str:
    try:
        return str(int(padded))
    except (TypeError, ValueError):
        return str(padded).lstrip("0") or "0"


def _has_active_bipd(raw) -> bool:
    """bipd_file is a zero-padded dollar-amount string (e.g. '00750'), not
    'Y'/'N'. A filing is active iff it parses to a positive number. Falls
    back to treating a literal 'Y' as active too, just in case some rows
    ever do use that encoding."""
    if raw is None:
        return False
    s = str(raw).strip()
    if not s:
        return False
    try:
        return float(s) > 0
    except ValueError:
        return s.upper() == "Y"


async def _get_bipd_map(dot_numbers: list[str]) -> dict[str, bool]:
    """
    Look up live BIPD-filing status for a batch of carriers from the
    Carrier-All-With-History dataset (6eyk-hxee), joined by dot_number.

    Returns {unpadded_dot_number: is_active_bool} so callers can match it
    directly against Company Census File rows (which use numeric,
    unpadded dot_number).
    """
    dot_numbers = sorted({str(d) for d in dot_numbers if d})
    if not dot_numbers:
        return {}

    result: dict[str, bool] = {}
    # Socrata handles a few hundred values in an IN() clause fine; chunk
    # defensively in case a caller ever passes a very large batch.
    for i in range(0, len(dot_numbers), 200):
        chunk = dot_numbers[i:i + 200]
        in_list = ",".join(f"'{_pad_dot(d)}'" for d in chunk)
        params = {
            "$where": f"dot_number in ({in_list})",
            "$select": "dot_number,bipd_file",
        }
        rows = await _get(LI_CARRIER_ID, params, limit=len(chunk))
        for r in rows:
            key = _unpad_dot(r.get("dot_number", ""))
            result[key] = _has_active_bipd(r.get("bipd_file", ""))
    return result


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
    # NOTE: bipd_file is NOT a column on the Company Census File (az4n-8mr2).
    # It only exists on the separate Carrier-All-With-History dataset
    # (6eyk-hxee), keyed by dot_number. It can't be added to this $where
    # clause -- doing so used to silently make Socrata error out (which is
    # why the filter/column showed nothing for every carrier). It's handled
    # below instead, via a join on dot_number.

    where = " AND ".join(clauses) if clauses else None
    order_map = {
        "dot_number": "dot_number ASC",
        "legal_name": "legal_name ASC",
        "power_units_desc": "power_units DESC",
        "mcs150_date": "mcs150_date DESC",
    }
    base_params = {"$order": order_map.get(order_by, "dot_number ASC")}
    if where:
        base_params["$where"] = where

    total_is_estimate = False

    if not bipd_only:
        params = {**base_params, "$offset": offset}
        rows = await _get(CENSUS_ID, params, limit=limit)

        count_params = {"$select": "count(*) as cnt"}
        if where:
            count_params["$where"] = where
        count_rows = await _get(CENSUS_ID, count_params, limit=1)
        total = int(count_rows[0]["cnt"]) if count_rows and "cnt" in count_rows[0] else len(rows)
    else:
        rows, total, total_is_estimate = await _search_with_bipd_filter(base_params, limit, offset)

    # Enrich this page with live BIPD-filing status, joined by dot_number.
    # This is what actually populates the "BIPD Filing" column -- the
    # census rows themselves never carry this field.
    bipd_map = await _get_bipd_map([str(r.get("dot_number", "")) for r in rows])

    carriers = []
    for r in rows:
        dot = str(r.get("dot_number", ""))
        carriers.append({
            "dot_number":        dot,
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
            "bipd_file":         "Y" if bipd_map.get(dot, False) else "",
            "fleetsize":         r.get("fleetsize", ""),
        })

    result = {"total": total, "carriers": carriers, "offset": offset, "limit": limit}
    if total_is_estimate:
        # We hit the scan cap before confirming there's nothing more; "total"
        # is a lower bound, not an exact count. See _search_with_bipd_filter.
        result["total_is_estimate"] = True
    return result


async def _search_with_bipd_filter(
    base_params: dict, limit: int, offset: int, max_scan_batches: int = 10
) -> tuple[list[dict], int, bool]:
    """
    Applies the "Active BIPD filing" filter on top of whatever else the
    person filtered by.

    Socrata can't join across datasets, and bipd_file only exists on
    6eyk-hxee while every other Market Explorer filter (state, status,
    operation, power units, hazmat, etc.) only exists on the census file
    (az4n-8mr2). So instead of one $where clause, we page through the
    census results that already match everything else, check each batch's
    BIPD status via a join query, and keep scanning until we've collected
    enough matches to fill the requested page (offset + limit).

    This makes results correct, but it means:
      - Requests are slower than a plain filter (multiple round trips).
      - If a very narrow combination of filters has few/no BIPD matches
        within max_scan_batches, we stop early and report an estimated
        (lower-bound) total rather than scanning millions of rows.

    The proper long-term fix is to ingest 6eyk-hxee into a local database
    alongside the census file (the project already has an ETL pipeline for
    SMS files) so this can become a real SQL join instead of a live-API
    scan -- worth doing if BIPD filtering gets heavy use.
    """
    batch_size = max(limit * 4, 200)
    scan_offset = 0
    collected: list[dict] = []
    exhausted = False

    for _ in range(max_scan_batches):
        batch = await _get(CENSUS_ID, {**base_params, "$offset": scan_offset}, limit=batch_size)
        if not batch:
            exhausted = True
            break
        scan_offset += len(batch)

        bipd_map = await _get_bipd_map([str(r.get("dot_number", "")) for r in batch])
        collected.extend(
            r for r in batch if bipd_map.get(str(r.get("dot_number", "")), False)
        )

        if len(batch) < batch_size:
            exhausted = True  # ran out of census rows matching the other filters
            break
        if len(collected) >= offset + limit:
            break

    page = collected[offset: offset + limit]
    total = len(collected)
    total_is_estimate = not exhausted and len(collected) < offset + limit
    return page, total, total_is_estimate


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