"""
Geocodes a US street address using the US Census Bureau Geocoding API.
Free, no API key required.
Returns (lat, lng) or None if geocoding fails.
"""

import httpx
import re

CENSUS_GEOCODE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


async def geocode_address(address: str) -> tuple[float, float] | None:
    """
    Geocode a US address string using Census Bureau API.
    Returns (lat, lng) or None on failure.
    """
    if not address or address.strip() == "":
        return None

    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(CENSUS_GEOCODE_URL, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            matches = data.get("result", {}).get("addressMatches", [])
            if not matches:
                return None
            coords = matches[0].get("coordinates", {})
            lat = coords.get("y")
            lng = coords.get("x")
            if lat and lng:
                return (float(lat), float(lng))
    except Exception as e:
        print(f"[Geocoder] Failed for '{address}': {e}")

    return None