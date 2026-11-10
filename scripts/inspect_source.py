"""Operator probe: inspect metadata, optionally request a model proposal; no data saved."""

import argparse
import asyncio
import json

from src.config import Settings
from src.discovery.inspection import inspect_source
from src.discovery.planner import ConnectorPlanningAgent
from src.http import ProviderError, SafeHTTP
from src.models import Place


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Reviewed official API metadata URL")
    parser.add_argument("--city", required=True)
    parser.add_argument("--country", required=True, help="ISO country code")
    parser.add_argument(
        "--ai", action="store_true", help="Call the configured model (optional)"
    )
    args = parser.parse_args()
    settings = Settings()
    place = Place(
        provider="operator",
        provider_id="metadata-probe",
        label=args.city,
        country=args.country,
        country_code=args.country.upper(),
        longitude=0,
        latitude=0,
        source_url=args.url,
    )
    try:
        async with asyncio.timeout(100), SafeHTTP(settings) as http:
            inspection = await inspect_source(args.url, http)
            result = {"inspection": inspection}
            if args.ai:
                result["proposal"] = await ConnectorPlanningAgent(http, settings).plan(
                    place, inspection
                )
            print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ProviderError, TimeoutError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": exc.message
                    if isinstance(exc, ProviderError)
                    else "Deadline exceeded",
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    asyncio.run(main())
