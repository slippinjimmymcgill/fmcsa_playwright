import asyncio
import traceback
from safer_scraper import get_carrier_by_dot

async def main():
    try:
        result = await get_carrier_by_dot("2033842", headless=False)
    except Exception as e:
        print("EXCEPTION TYPE:", type(e).__name__)
        print("EXCEPTION REPR:", repr(e))
        traceback.print_exc()

asyncio.run(main())