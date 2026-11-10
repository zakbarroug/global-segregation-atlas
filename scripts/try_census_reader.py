"""Live generic reader + optional configured-model trial, using official ACS in RAM.

Prints only schemas/check outcomes; never writes fetched records or maps.
The San Francisco county probe does not itself prove a municipal footprint.
Run from project root: .venv/Scripts/python scripts/try_census_reader.py [--ai]
"""

import argparse
import asyncio
import json

from src.config import Settings
from src.http import ProviderError, SafeHTTP
from src.ingestion.probe import probe_table
from src.ingestion.readers import ReaderSpec
from src.models import Place


async def run(use_ai):
    settings = Settings()
    place = Place(
        provider="operator",
        provider_id="reader-probe",
        label="San Francisco",
        country="United States",
        country_code="US",
        latitude=37.77,
        longitude=-122.42,
        source_url="https://www.census.gov/",
    )
    base = f"https://api.census.gov/data/{settings.acs_year}/acs/acs5"
    columns = [f"B19001_{i:03d}E" for i in range(1, 18)]
    params = {
        "get": ",".join(["NAME", *columns]),
        "for": "tract:*",
        "in": "state:06 county:075",
    }
    if settings.census_api_key.get_secret_value():
        params["key"] = settings.census_api_key.get_secret_value()
    async with asyncio.timeout(110), SafeHTTP(settings) as http:
        metadata = await http.json(base + "/groups/B19001.json", max_bytes=1_000_000)
        result = await probe_table(
            place,
            base,
            ReaderSpec(format="json"),
            settings,
            http,
            params=params,
            field_metadata=metadata["variables"],
            use_ai=use_ai,
        )
    proposal = result.get("proposal") or {}
    print(
        json.dumps(
            {
                "format": result["inspection"]["format"],
                "rows_read": result["inspection"]["row_count"],
                "model_requested": use_ai,
                "proposal_status": proposal.get("status"),
                "attempts": proposal.get("attempts"),
                "data_validation": proposal.get("data_validation"),
                "checks": proposal.get("checks"),
                "activated": result["activated"],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ai", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.ai))
    except (ProviderError, TimeoutError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "code": getattr(exc, "code", "timeout"),
                    "reason": getattr(exc, "message", "Deadline exceeded"),
                }
            )
        )
        raise SystemExit(1) from None
