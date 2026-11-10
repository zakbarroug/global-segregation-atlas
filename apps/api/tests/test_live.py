"""Explicitly opt in with RUN_LIVE_TESTS=1. Fetched observations remain in memory."""

import os

import pytest

from src.config import Settings
from src.geography.places import PlaceTokens, search_places
from src.http import SafeHTTP
from src.models import AnalysisRequest
from src.pipeline import analysis_events


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="Live tests are explicitly opt-in")
@pytest.mark.parametrize("city,minimum_areas", [("New York", 1000), ("San Francisco", 100)])
async def test_real_official_data(city, minimum_areas):
    settings = Settings()
    if not settings.census_api_key.get_secret_value():
        pytest.skip("CENSUS_API_KEY required")
    async with SafeHTTP(settings) as http:
        places = await search_places(city, http, settings, PlaceTokens("live-test"))
        place = next(
            p
            for p in places
            if p.country_code == "US"
            and (
                p.provider_id in {"R:175905", "N:61785451", "5128581"}
                if city == "New York"
                else abs(p.longitude + 122.4194) < 0.1
            )
        )
        metrics, complete, mapped = [], False, False
        async for item in analysis_events(
            place, AnalysisRequest(city_id=place.city_id), settings, http
        ):
            if item.event == "map_ready":
                assert item.data["coverage"]["fraction"] == 1
                assert item.data["coverage"]["areas"] > minimum_areas
                assert item.data["coverage"]["households"] > 100000
                mapped = True
            if item.event == "metric_computed":
                assert item.data["metric"]["value"] is not None
                assert 0 <= item.data["metric"]["value"] <= 1
                metrics.append(item.data["metric"]["id"])
            assert item.event not in {"failed", "insufficient_data"}
            if item.event == "complete":
                complete = item.data["status"] == "measured"
        assert complete and mapped and len(metrics) == 5
