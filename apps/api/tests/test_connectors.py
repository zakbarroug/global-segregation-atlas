import copy

import httpx
import pytest

from src.connectors.census import COUNTIES, CensusNYCConnector
from src.geography.validation import checked_polygon, join_and_validate
from src.http import ProviderError, SafeHTTP

from .provider_fixtures import income_table, official_handler, polygon
from .test_http import allow_dns


async def test_full_synthetic_connector_pagination_and_join(settings, nyc):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return official_handler(request)

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        connector = CensusNYCConnector(http, settings)
        source = (await connector.discover(nyc, 2024))[0]
        data = connector.normalize(await connector.fetch(source, nyc), source, nyc)
        tracts = await connector.get_boundaries(2024)
        counties = await connector.get_boundaries(2024, "Counties")
        features, coverage, warnings = join_and_validate(data, tracts, counties)
    assert coverage["fraction"] == 1 and len(features["features"]) == 10
    assert (
        sum(path.endswith("/777/query") for path in calls) == 15
    )  # five count + ten paginated requests
    assert coverage["households"] == 1360
    assert features["features"][0]["properties"]["low_share"] == pytest.approx(21 / 136)
    assert warnings and all(f["geometry"]["type"] == "Polygon" for f in features["features"])


@pytest.mark.parametrize(
    "problem",
    ["negative", "missing", "total", "duplicate", "wrong_county", "partial_county", "malformed"],
)
async def test_malformed_income_rejected(problem, settings, nyc):
    async with SafeHTTP(
        settings, transport=httpx.MockTransport(official_handler), dns_check=allow_dns
    ) as http:
        connector = CensusNYCConnector(http, settings)
        source = (await connector.discover(nyc, 2024))[0]
        raw = [income_table(c) for c in COUNTIES]
        if problem == "negative":
            raw[0][1][3] = "-666666666"
        if problem == "missing":
            raw[0][1][3] = None
        if problem == "total":
            raw[0][1][1] = "99999"
        if problem == "duplicate":
            raw[0].append(raw[0][1])
        if problem == "wrong_county":
            raw[0][1][-2] = "999"
        if problem == "partial_county":
            raw.pop()
        if problem == "malformed":
            raw[0][1].pop()
        with pytest.raises(ProviderError):
            connector.normalize(raw, source, nyc)


async def test_missing_moe_is_flagged_not_imputed(settings, nyc):
    async with SafeHTTP(
        settings, transport=httpx.MockTransport(official_handler), dns_check=allow_dns
    ) as http:
        connector = CensusNYCConnector(http, settings)
        source = (await connector.discover(nyc, 2024))[0]
        raw = [income_table(c) for c in COUNTIES]
        raw[0][1][4] = "-555555555"
        result = connector.normalize(raw, source, nyc)
        assert result.areas[0].margins_of_error[0] is None
        assert "some_margins_of_error_unavailable" in result.areas[0].quality_flags


@pytest.mark.parametrize(
    "problem", ["missing_polygon", "extra_polygon", "vintage", "overlap", "outside"]
)
async def test_geometry_validation_refuses_invalid_city(problem, settings, nyc):
    async with SafeHTTP(
        settings, transport=httpx.MockTransport(official_handler), dns_check=allow_dns
    ) as http:
        connector = CensusNYCConnector(http, settings)
        source = (await connector.discover(nyc, 2024))[0]
        data = connector.normalize([income_table(c) for c in COUNTIES], source, nyc)
        tracts = await connector.get_boundaries(2024)
        counties = await connector.get_boundaries(2024, "Counties")
        if problem == "missing_polygon":
            tracts["features"].pop()
        if problem == "extra_polygon":
            extra = copy.deepcopy(tracts["features"][0])
            extra["properties"]["GEOID"] = "36999000001"
            tracts["features"].append(extra)
        if problem == "vintage":
            tracts["provenance"]["year"] = 2023
        if problem == "overlap":
            tracts["features"][1]["geometry"] = tracts["features"][0]["geometry"]
        if problem == "outside":
            tracts["features"][0]["geometry"] = polygon(-80, 40)
        with pytest.raises(ProviderError):
            join_and_validate(data, tracts, counties)


def test_invalid_crs_rejected():
    with pytest.raises(ProviderError):
        checked_polygon(polygon(1000000, 2000000))


async def test_changed_metadata_refused(settings, nyc):
    def handler(request):
        response = official_handler(request)
        if request.url.path.endswith("B19001.json"):
            body = response.json()
            body["variables"]["B19001_002E"]["label"] = "Median individual wages"
            return httpx.Response(200, json=body)
        return response

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        with pytest.raises(ProviderError):
            await CensusNYCConnector(http, settings).discover(nyc, 2024)


def test_nyc_is_not_every_new_york(settings, nyc):
    connector = CensusNYCConnector(None, settings)
    assert connector.supports(nyc)[0] == 1
    assert connector.supports(nyc.model_copy(update={"provider_id": "R:other"}))[0] == 0
