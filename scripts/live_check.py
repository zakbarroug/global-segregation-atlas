"""Opt-in live vertical slice, with summary-only output and no saved datasets."""

import asyncio
import sys

from src.config import Settings
from src.geography.places import PlaceTokens, search_places
from src.http import SafeHTTP
from src.models import AnalysisRequest
from src.pipeline import analysis_events


async def run():
    settings = Settings()
    succeeded = False
    async with SafeHTTP(settings) as http:
        places = await search_places(
            "New York", http, settings, PlaceTokens("live-check")
        )
        place = next(
            p
            for p in places
            if p.country_code == "US"
            and p.provider_id in {"R:175905", "N:61785451", "5128581"}
        )
        async for item in analysis_events(
            place, AnalysisRequest(city_id=place.city_id), settings, http
        ):
            info = {"event": item.event}
            if item.event == "map_ready":
                info["coverage"] = item.data["coverage"]
            if item.event == "metric_computed":
                info["metric"] = {
                    k: item.data["metric"][k] for k in ["id", "unavailable_reason"]
                }
                info["metric"]["available"] = item.data["metric"]["value"] is not None
            if item.event in ("failed", "insufficient_data"):
                info.update(
                    {k: v for k, v in item.data.items() if k in {"code", "reason"}}
                )
            if item.event == "complete":
                info["status"] = item.data["status"]
                succeeded = item.data["status"] == "measured"
            print(info, flush=True)
    return 0 if succeeded else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
