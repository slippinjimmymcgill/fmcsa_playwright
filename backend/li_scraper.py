"""
Fetches Insurance History and Authority History from FMCSA datasets
on the DOT Open Data Portal (data.transportation.gov) via Socrata API.

Confirmed dataset IDs (from catalog.data.gov):
  InsHist - All With History:  nzpz-e5xn  (legacy, text/plain download only)
  AuthHist - All With History: 9mw4-x3tu  (legacy, has Socrata JSON API)
  Motus InsHist - All With History: uses USDOT_NUMBER field

AuthHist confirmed field names from columns.json:
  dot_number (8-digit zero-padded), docket_number, mod_col_1 (OP_AUTH_TYPE),
  original_action_desc, orig_served_date, disp_action_desc,
  disp_decided_date, disp_served_date

InsHist field names (from FMCSA data dictionary):
  DOT_NUMBER, DOCKET_NUMBER, TYPE_OF_INS, POLICY_NUMBER,
  EFFECTIVE_DATE, CANCEL_EFFECTIVE_DATE, CANCEL_METHOD,
  INS_COMPANY_NAME (or INS_COMPANY)
"""

import httpx

SOCRATA_BASE = "https://data.transportation.gov/resource"

# Confirmed real dataset IDs
AUTHHIST_ID = "9mw4-x3tu"  # AuthHist - legacy, confirmed working Socrata API
INSHIST_ID  = "xkn3-5fci"  # InsHist - legacy Socrata queryable dataset
MOTUS_INSHIST_ID = "nzpz-e5xn"  # Motus InsHist (may be text/plain only)

HEADERS = {"Accept": "application/json"}


def _pad_dot(dot_number: str) -> str:
    """AuthHist stores DOT numbers as 8-digit zero-padded strings."""
    return dot_number.zfill(8)


async def _socrata_get(dataset_id: str, where: str, limit: int = 100) -> list[dict]:
    """Query a Socrata dataset with a SoQL WHERE clause."""
    url = f"{SOCRATA_BASE}/{dataset_id}.json"
    params = {"$where": where, "$limit": limit}
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
            resp = await client.get(url, params=params)
            print(f"[LI] {dataset_id} status={resp.status_code} url={resp.url}")
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
            else:
                print(f"[LI] Error body: {resp.text[:300]}")
    except Exception as e:
        print(f"[LI] Request failed for {dataset_id}: {e}")
    return []


async def get_li_data(dot_number: str) -> dict:
    padded_dot = _pad_dot(dot_number)

    # ------------------------------------------------------------------ #
    # Insurance History
    # Try multiple field name variants since they differ between datasets
    # ------------------------------------------------------------------ #
    insurance_raw = []

    # Try xkn3-5fci (legacy InsHist - known Socrata queryable)
    rows = await _socrata_get(
        INSHIST_ID,
        f"dot_number='{padded_dot}'"
    )
    if rows:
        insurance_raw = rows
        print(f"[LI] Insurance from {INSHIST_ID}: {len(rows)} records")
    else:
        # Try unpadded
        rows = await _socrata_get(INSHIST_ID, f"dot_number='{dot_number}'")
        if rows:
            insurance_raw = rows
        else:
            # Try Motus InsHist with USDOT_NUMBER
            rows = await _socrata_get(
                MOTUS_INSHIST_ID,
                f"usdot_number='{dot_number}'"
            )
            if rows:
                insurance_raw = rows
                print(f"[LI] Insurance from Motus {MOTUS_INSHIST_ID}: {len(rows)} records")

    # ------------------------------------------------------------------ #
    # Authority History - confirmed fields from columns.json:
    # dot_number (8-digit padded), docket_number, mod_col_1 (auth type),
    # original_action_desc, orig_served_date,
    # disp_action_desc, disp_decided_date, disp_served_date
    # ------------------------------------------------------------------ #
    rows = await _socrata_get(
        AUTHHIST_ID,
        f"dot_number='{padded_dot}'"
    )
    authority_raw = rows
    if not authority_raw:
        # Try unpadded just in case
        rows = await _socrata_get(AUTHHIST_ID, f"dot_number='{dot_number}'")
        authority_raw = rows

    print(f"[LI] Authority: {len(authority_raw)} records")

    # ------------------------------------------------------------------ #
    # Normalize insurance - try both old and new field names
    # ------------------------------------------------------------------ #
    ins_normalized = []
    for row in insurance_raw:
        ins_normalized.append({
            "effective": (
                row.get("effective_date") or
                row.get("eff_date") or ""
            ),
            "cancel_effective": (
                row.get("cancel_effective_date") or
                row.get("cancel_eff_date") or ""
            ),
            "insurer": (
                row.get("ins_company_name") or
                row.get("ins_company") or
                row.get("insurance_company") or
                row.get("company_name") or ""
            ),
            "policy": (
                row.get("policy_number") or
                row.get("policy_surety_number") or ""
            ),
            "coverage": (
                row.get("type_of_ins") or
                row.get("insurance_type") or
                row.get("ins_type") or
                row.get("coverage") or ""
            ),
            "cancel_method": (
                row.get("cancel_method") or
                row.get("cancellation_method") or
                row.get("filing_status_reason") or ""
            ),
        })

    # ------------------------------------------------------------------ #
    # Normalize authority - using confirmed field names
    # ------------------------------------------------------------------ #
    auth_normalized = []
    for row in authority_raw:
        auth_normalized.append({
            "served":    row.get("orig_served_date") or row.get("disp_served_date") or "",
            "decided":   row.get("disp_decided_date") or "",
            "docket":    row.get("docket_number") or "",
            "authority": row.get("mod_col_1") or row.get("op_auth_type") or "",
            "action":    row.get("original_action_desc") or "",
        })

    return {
        "insurance_history": ins_normalized,
        "authority_history": auth_normalized,
    }