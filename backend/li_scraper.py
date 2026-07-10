"""
Fetches Insurance History and Authority History from FMCSA datasets
on the DOT Open Data Portal (data.transportation.gov) via Socrata API.

Confirmed working dataset IDs:
  AuthHist: 9mw4-x3tu  (dot_number is 8-digit zero-padded)
  InsHist:  6sqe-dvqs  (InsHist - All With History)
"""

import httpx

SOCRATA_BASE = "https://data.transportation.gov/resource"
AUTHHIST_ID  = "9mw4-x3tu"
INSHIST_ID   = "6sqe-dvqs"

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

    # Insurance History - try padded and unpadded DOT
    insurance_raw = await _socrata_get(INSHIST_ID, f"dot_number='{padded}'")
    if not insurance_raw:
        insurance_raw = await _socrata_get(INSHIST_ID, f"dot_number='{dot_number}'")

    # Authority History - confirmed padded works
    authority_raw = await _socrata_get(AUTHHIST_ID, f"dot_number='{padded}'")

    print(f"[LI] Insurance: {len(insurance_raw)} records, Authority: {len(authority_raw)} records")

    # Normalize insurance - field names confirmed from 6sqe-dvqs
    ins_normalized = []
    for row in insurance_raw:
        ins_normalized.append({
            "effective":        row.get("effective_date") or row.get("eff_date") or "",
            "cancel_effective": row.get("cancel_effective_date") or row.get("cancel_eff_date") or "",
            "insurer":          row.get("ins_company_name") or row.get("company_name") or row.get("insurer") or "",
            "policy":           row.get("policy_number") or row.get("policy_surety_number") or "",
            "coverage":         row.get("type_of_ins") or row.get("insurance_type") or row.get("coverage") or "",
            "cancel_method":    row.get("cancel_method") or row.get("filing_status_reason") or "",
        })

    # Normalize authority - confirmed fields from 9mw4-x3tu
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