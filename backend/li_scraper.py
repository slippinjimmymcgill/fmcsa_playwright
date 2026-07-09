"""
Fetches Insurance History, Authority History, and Mileage from
FMCSA datasets on the DOT Open Data Portal (data.transportation.gov).

Uses Socrata JSON API - no API key required, no scraping, no Playwright.
Filters by USDOT number using SoQL WHERE clause.

Datasets used:
- InsHist (Motus): https://data.transportation.gov/resource/rqg5-mte8.json
- AuthHist (Motus): https://data.transportation.gov/resource/a37f-s6p3.json
- Legacy InsHist:   https://data.transportation.gov/resource/xkn3-5fci.json
- Legacy AuthHist:  https://data.transportation.gov/resource/a7vf-2rp3.json
"""

import httpx

SOCRATA_BASE = "https://data.transportation.gov/resource"

# Dataset IDs - Motus (modern) first, legacy as fallback
INSHIST_IDS = ["rqg5-mte8", "xkn3-5fci"]
AUTHHIST_IDS = ["a37f-s6p3", "a7vf-2rp3"]

HEADERS = {
    "Accept": "application/json",
    "X-App-Token": "",  # optional - add token for higher rate limits
}


async def _fetch_socrata(dataset_id: str, dot_number: str, limit: int = 100) -> list[dict]:
    """Fetch records from a Socrata dataset filtered by USDOT number."""
    url = f"{SOCRATA_BASE}/{dataset_id}.json"
    params = {
        "$where": f"usdot_number='{dot_number}'",
        "$limit": limit,
        "$order": ":id DESC",
    }
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
    return []


async def get_li_data(dot_number: str) -> dict:
    """
    Fetch insurance and authority history from DOT Open Data Portal.
    Tries Motus (modern) datasets first, falls back to legacy datasets.
    """
    insurance_raw = []
    authority_raw = []

    # Try insurance datasets
    for ds_id in INSHIST_IDS:
        try:
            rows = await _fetch_socrata(ds_id, dot_number)
            if rows:
                insurance_raw = rows
                print(f"[LI] Insurance: {len(rows)} records from dataset {ds_id}")
                break
        except Exception as e:
            print(f"[LI] Insurance dataset {ds_id} failed: {e}")

    # Try authority datasets
    for ds_id in AUTHHIST_IDS:
        try:
            rows = await _fetch_socrata(ds_id, dot_number)
            if rows:
                authority_raw = rows
                print(f"[LI] Authority: {len(rows)} records from dataset {ds_id}")
                break
        except Exception as e:
            print(f"[LI] Authority dataset {ds_id} failed: {e}")

    # Normalize insurance records
    # Socrata field names vary between Motus and legacy schemas
    ins_normalized = []
    for row in insurance_raw:
        ins_normalized.append({
            "effective": (
                row.get("effective_date") or
                row.get("effective") or
                row.get("eff_date") or ""
            ),
            "cancel_effective": (
                row.get("cancel_effective_date") or
                row.get("cancel_effective") or
                row.get("cancellation_effective_date") or ""
            ),
            "insurer": (
                row.get("ins_company_name") or
                row.get("insurer") or
                row.get("insurance_company") or
                row.get("company_name") or ""
            ),
            "policy": (
                row.get("policy_number") or
                row.get("policy_surety_number") or
                row.get("policy_no") or ""
            ),
            "coverage": (
                row.get("coverage") or
                row.get("insurance_type") or
                row.get("type_of_insurance") or
                row.get("ins_type") or ""
            ),
            "cancel_method": (
                row.get("cancel_method") or
                row.get("cancellation_method") or
                row.get("filing_status_reason") or ""
            ),
        })

    # Normalize authority records
    auth_normalized = []
    for row in authority_raw:
        auth_normalized.append({
            "served": (
                row.get("served_date") or
                row.get("date_served") or
                row.get("served") or ""
            ),
            "decided": (
                row.get("decided_date") or
                row.get("decision_date") or
                row.get("decided") or
                row.get("original_action_date") or ""
            ),
            "docket": (
                row.get("docket_number") or
                row.get("mc_number") or
                row.get("docket_no") or ""
            ),
            "authority": (
                row.get("authority_type") or
                row.get("op_auth_type") or
                row.get("authority") or ""
            ),
            "action": (
                row.get("action") or
                row.get("original_action") or
                row.get("op_auth_status") or ""
            ),
        })

    return {
        "insurance_history": ins_normalized,
        "authority_history": auth_normalized,
    }