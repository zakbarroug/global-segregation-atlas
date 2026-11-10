"""Live city-only acceptance audit. Prints evidence/status, never observations.

Usage: .venv/Scripts/python scripts/audit_city_discovery.py Vienna --country AT
Success of search is reported separately from success of measurement.
"""

import argparse
import asyncio
import json

from src.config import Settings
from src.discovery.exploration import explore_web
from src.geography.places import PlaceTokens, search_places
from src.http import ProviderError, SafeHTTP
from src.models import AnalysisRequest
from src.pipeline import analysis_events


async def run(args):
    settings = Settings()
    async with SafeHTTP(settings) as http:
        places = await search_places(
            args.city, http, settings, PlaceTokens("city-audit-session")
        )
        matches = [p for p in places if p.country_code == args.country.upper()]
        if len(matches) != 1:
            raise ProviderError(
                "audit_ambiguity",
                "La recherche doit identifier une seule ville dans ce pays ; préciser son nom.",
            )
        place = matches[0]
        print(
            json.dumps(
                {
                    "event": "city_resolved",
                    "city": place.label,
                    "country": place.country_code,
                }
            ),
            flush=True,
        )
        if args.research_only:
            result = await explore_web(place, settings, http)
            print(
                json.dumps({"event": "research_audit", **result}, ensure_ascii=True),
                flush=True,
            )
            return
        mapped, metrics = False, 0
        async for item in analysis_events(
            place, AnalysisRequest(city_id=place.city_id), settings, http
        ):
            if item.event == "map_ready":
                mapped = True
            elif item.event == "metric_computed":
                metrics += item.data["metric"]["value"] is not None
            elif item.event == "discovery_progress":
                print(
                    json.dumps(
                        {
                            "event": item.event,
                            "agent": item.data["agent"],
                            "status": item.data["status"],
                            "message": item.data["message"],
                        },
                        ensure_ascii=True,
                    ),
                    flush=True,
                )
            elif item.event == "insufficient_data":
                web = item.data.get("web_discovery", {})
                print(
                    json.dumps(
                        {
                            "event": "discovery_audit",
                            "search_status": web.get("status"),
                            "queries": web.get("queries"),
                            "visited_sources": web.get("pages"),
                            "selected_ids": web.get("selected_source_ids"),
                            "missing": item.data.get("missing"),
                        },
                        ensure_ascii=True,
                    ),
                    flush=True,
                )
            elif item.event in {"failed", "complete"}:
                print(
                    json.dumps(
                        {
                            "event": item.event,
                            **item.data,
                            "map_validated": mapped,
                            "metrics_computed": metrics,
                            "full_requirement_met": mapped and metrics == 5,
                        },
                        ensure_ascii=True,
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city")
    parser.add_argument("--country", required=True)
    parser.add_argument("--research-only", action="store_true")
    try:
        asyncio.run(run(parser.parse_args()))
    except (ProviderError, TimeoutError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "code": getattr(exc, "code", "timeout"),
                    "reason": getattr(exc, "message", "Deadline exceeded"),
                },
                ensure_ascii=True,
            )
        )
        raise SystemExit(1) from None
