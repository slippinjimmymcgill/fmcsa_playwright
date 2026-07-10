"""
Fetches Insurance History and Authority History from FMCSA datasets
on the DOT Open Data Portal (data.transportation.gov) via Socrata API.

Confirmed working dataset IDs (from debug-socrata + DOT Hub UI):
  InsHist:  6sqe-dvqs  (padded 8-digit DOT, e.g. '03576562')
  AuthHist: 9mw4-x3tu  (padded 8-digit DOT)
  Motus InsHist:  qh9u-swkp (try unpadded USDOT_NUMBER)
  Motus AuthHist: 6eyk-hxee (try unpadded USDOT_NUMBER)

Confirmed InsHist field names from debug-socrata sample:
  name_company, policy_no, effective_date, cancl_effective_date,
  cancl_method, mod_col_3 (coverage type), ins_form_code
"""

import httpx

SOCRATA_BASE = "https://data.transportation.gov/resource"

INSHIST_IDS  = ["6sqe-dvqs", "qh9u-swkp"]
AUTHHIST_IDS = ["9mw4-x3tu", "6eyk-hxee"]

HEADERS = {"Accept": "application/json"}


def _pad_dot(dot_number: str) -> str:
    return dot_number.zfill(8)


async def _socrata_get(dataset_id: str, where: str, limit: int = 100) -> list[dict]:
    url = f"{SOCRATA_BASE}/{dataset_id}.json"
    params = {"$where": where, "$limit": limit}
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
            resp = await client.get(url, params=params)
            print(f"[LI] {dataset_id} status={resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
            else:
                print(f"[LI] Error: {resp.text[:200]}")
    except Exception as e:
        print(f"[LI] Request failed for {dataset_id}: {e}")
    return []


async def get_li_data(dot_number: str) -> dict:
    padded = _pad_dot(dot_number)

    # Insurance History
    insurance_raw = []
    for ds_id in INSHIST_IDS:
        rows = await _socrata_get(ds_id, f"dot_number='{padded}'")
        if not rows:
            # Try unpadded and USDOT_NUMBER variants
            rows = await _socrata_get(ds_id, f"usdot_number='{dot_number}'")
        if rows:
            insurance_raw = rows
            print(f"[LI] Insurance: {len(rows)} records from {ds_id}")
            break

    # Authority History
    authority_raw = []
    for ds_id in AUTHHIST_IDS:
        rows = await _socrata_get(ds_id, f"dot_number='{padded}'")
        if not rows:
            rows = await _socrata_get(ds_id, f"usdot_number='{dot_number}'")
        if rows:
            authority_raw = rows
            print(f"[LI] Authority: {len(rows)} records from {ds_id}")
            break

    # Normalize insurance - confirmed field names from 6sqe-dvqs
    ins_normalized = []
    for row in insurance_raw:
        ins_normalized.append({
            "effective":        row.get("effective_date", ""),
            "cancel_effective": row.get("cancl_effective_date", ""),
            "insurer":          row.get("name_company", ""),
            "policy":           row.get("policy_no", ""),
            "coverage":         row.get("mod_col_3", ""),
            "cancel_method":    row.get("cancl_method", ""),
        })

    # Normalize authority - confirmed field names from 9mw4-x3tu
    auth_normalized = []
    for row in authority_raw:
        auth_normalized.append({
            "served":    row.get("orig_served_date", ""),
            "decided":   row.get("disp_decided_date", ""),
            "docket":    row.get("docket_number", ""),
            "authority": row.get("mod_col_1", ""),
            "action":    row.get("original_action_desc", ""),
        })

    return {
        "insurance_history": ins_normalized,
        "authority_history": auth_normalized,
    }