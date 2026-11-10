"""Synthetic protocol/geometry fixtures; never imported in production."""

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from src.discovery.census_builder import build_census_connector
from src.discovery.inspection import PageMetadata, inspect_source, search_catalog
from src.discovery.planner import ConnectorPlanningAgent, compatible_json, configured_endpoint
from src.discovery.recipes import ConnectorRecipe, check_recipe
from src.http import ProviderError, SafeHTTP

from .provider_fixtures import polygon
from .test_http import allow_dns


def builder_handler(*, mismatch=False, wrong_name=False, wrong_state=False):
    def handler(request):
        path = request.url.path
        if path.endswith("/MapServer"):
            return httpx.Response(
                200,
                json={
                    "layers": [
                        {"id": 91, "name": "Incorporated Places"},
                        {"id": 92, "name": "Counties"},
                    ]
                },
            )
        is_county = "/92" in path
        if not path.endswith("/query"):
            return httpx.Response(
                200,
                json={
                    "fields": [
                        {"name": f}
                        for f in [
                            "GEOID",
                            "NAME",
                            "BASENAME",
                            "STATE",
                            "COUNTY" if is_county else "PLACE",
                        ]
                    ],
                    "geometryType": "esriGeometryPolygon",
                },
            )
        props = {
            "STATE": "06",
            "GEOID": "06075" if is_county else "0667000",
            "COUNTY": "075",
            "NAME": "Synthetic city",
            "BASENAME": "Different city" if wrong_name else "Synthetic City",
        }
        if wrong_state and is_county:
            props["STATE"] = "36"
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": props,
                        "geometry": polygon(
                            -122.5, 37.7, 0.4 if mismatch and is_county else 0.2, 0.2
                        ),
                    }
                ],
            },
        )

    return handler


async def test_auto_connector_requires_exact_official_identity_and_geometry(settings, nyc):
    place = nyc.model_copy(
        update={"label": "Synthetic City", "longitude": -122.4, "latitude": 37.8}
    )
    async with SafeHTTP(
        settings, transport=httpx.MockTransport(builder_handler()), dns_check=allow_dns
    ) as http:
        connector, report = await build_census_connector(place, 2024, http, settings)
        assert connector.state == "06" and connector.counties == ("075",)
        assert report["activated"] and report["recipe"]["municipal_geoid"] == "0667000"
        assert (await connector.get_extent(2024))["provenance"][
            "equivalence"
        ] == "exact_topological_equality"
        assert len(connector.outline(await connector.get_extent(2024))["features"]) == 1
        with pytest.raises(ProviderError):
            await connector.get_extent(2023)


@pytest.mark.parametrize(
    "option,code",
    [
        ("mismatch", "builder_extent"),
        ("wrong_name", "builder_identity"),
        ("wrong_state", "builder_identifiers"),
    ],
)
async def test_no_county_proxy_for_a_different_city(option, code, settings, nyc):
    place = nyc.model_copy(
        update={"label": "Synthetic City", "longitude": -122.4, "latitude": 37.8}
    )
    async with SafeHTTP(
        settings,
        transport=httpx.MockTransport(builder_handler(**{option: True})),
        dns_check=allow_dns,
    ) as http:
        with pytest.raises(ProviderError) as error:
            await build_census_connector(place, 2024, http, settings)
    assert error.value.code == code


def recipe_data():
    return {
        "template": "arcgis",
        "source_url": "https://tigerweb.geo.census.gov/test/MapServer/2",
        "title": "Synthetic income",
        "year": 2024,
        "bindings": [
            {"role": "income_count", "field": field, "meaning": "Synthetic household income count"}
            for field in ("LOW", "HIGH")
        ],
        "evidence": [],
        "missing": [],
    }


def inspection():
    return {
        "url": recipe_data()["source_url"],
        "format": "arcgis",
        "fields": [{"name": "LOW"}, {"name": "HIGH"}],
        "resources": [],
    }


def test_recipe_never_self_authorizes_license_or_activation():
    report = check_recipe(ConnectorRecipe.model_validate(recipe_data()), inspection())
    assert report["status"] == "requires_review" and report["activated"] is False
    with pytest.raises(ValidationError):
        ConnectorRecipe.model_validate({**recipe_data(), "permissions": "public_domain"})
    with pytest.raises(ValidationError):
        ConnectorRecipe.model_validate({**recipe_data(), "code": "arbitrary Python"})


def test_housing_units_cannot_be_promoted_to_income_counts():
    data = recipe_data()
    data["bindings"][0]["field"] = "HU100"
    source = inspection()
    source["fields"].append({"name": "HU100", "label": "Housing units"})
    assert check_recipe(ConnectorRecipe.model_validate(data), source)["status"] == "rejected"


@pytest.mark.parametrize("mutation", ["field", "url", "duplicate", "median"])
def test_reject_invented_fields_and_insufficient_distributions(mutation):
    data = recipe_data()
    if mutation == "field":
        data["bindings"][0]["field"] = "INVENTED"
    if mutation == "url":
        data["source_url"] = "https://evil.test"
    if mutation == "duplicate":
        data["bindings"][1]["field"] = "LOW"
    if mutation == "median":
        data["bindings"] = []
    assert check_recipe(ConnectorRecipe.model_validate(data), inspection())["status"] == (
        "blocked" if mutation == "median" else "rejected"
    )


async def test_model_can_repair_once_without_raw_observations(settings, vienna):
    settings.enable_ai_discovery = True
    settings.openai_api_key = type(settings.openai_api_key)("synthetic-secret")
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["store"] is False and "income_counts" not in request.content.decode()
        recipe = recipe_data()
        if len(calls) == 1:
            recipe["bindings"][0]["field"] = "INVENTED"
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(recipe)}],
                    }
                ]
            },
        )

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        result = await ConnectorPlanningAgent(http, settings).plan(vienna, inspection())
    assert len(calls) == 2 and result["status"] == "requires_review"


@pytest.mark.parametrize(
    "url,allow",
    [
        ("http://192.168.1.1/v1", False),
        ("http://127.0.0.1:11434/v1", False),
        ("https://user:pass@example.com/v1", False),
        ("https://example.com/v1?token=a", False),
    ],
)
def test_endpoint_only_accepts_explicit_safe_configuration(settings, url, allow):
    settings.ai_base_url, settings.ai_allow_local = url, allow
    with pytest.raises(ProviderError):
        configured_endpoint(settings)


def test_local_endpoint_requires_explicit_opt_in(settings):
    settings.ai_base_url, settings.ai_allow_local = "http://127.0.0.1:11434/v1", True
    assert configured_endpoint(settings)[2] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "paid/model"},
        {"model": "openrouter/free", "models": ["paid/model"]},
        {"model": "openrouter/free", "plugins": [{"id": "web"}]},
    ],
)
async def test_paid_fallbacks_refused_before_any_network(settings, payload):
    settings.ai_base_url = "https://openrouter.ai/api/v1"
    with pytest.raises(ProviderError) as error:
        await compatible_json(settings, payload, SimpleNamespace(received=0))
    assert error.value.code == "ai_paid_model"


async def test_compatible_protocol_and_429_do_not_leak_body_or_key(settings, monkeypatch):
    settings.ai_base_url = "https://openrouter.ai/api/v1"
    settings.ai_api_key = type(settings.ai_api_key)("synthetic-secret")
    original = httpx.AsyncClient
    monkeypatch.setattr("src.discovery.planner.public_dns", allow_dns)

    def factory(**kwargs):
        def handler(request):
            assert request.headers["Authorization"] == "Bearer synthetic-secret"
            assert request.url.path == "/api/v1/chat/completions"
            return httpx.Response(429, json={"error": "synthetic-secret must never leak"})

        return original(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("src.discovery.planner.httpx.AsyncClient", factory)
    with pytest.raises(ProviderError) as error:
        await compatible_json(
            settings, {"model": "xingchen-agi/xing4.0-29b-a4b:free"}, SimpleNamespace(received=0)
        )
    assert error.value.code == "ai_rate_limit" and "synthetic-secret" not in str(error.value)


async def test_arcgis_inspection_extracts_schema_not_records(settings):
    def handler(request):
        assert not request.url.path.endswith("query")
        return httpx.Response(
            200,
            json={
                "name": "Synthetic layer",
                "fields": [
                    {"name": "LOW", "alias": "Low household count", "type": "esriFieldTypeInteger"}
                ],
                "features": [{"private": "do not pass"}],
                "geometryType": "esriGeometryPolygon",
            },
        )

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        result = await inspect_source(recipe_data()["source_url"], http)
    assert result["fields"][0]["name"] == "LOW" and "do not pass" not in json.dumps(result)


def test_html_metadata_never_copies_tables_scripts_or_unsafe_links():
    parser = PageMetadata("https://www.statistik.at/")
    parser.feed(
        '<title>Income</title><meta name="description" content="Official metadata"><table><td>private observation</td></table><script>malicious code</script><a href="http://127.0.0.1/FeatureServer/2">attack</a>'
    )
    assert parser.title == "Income" and not parser.resources
    assert "private observation" not in parser.description


async def test_ckan_search_and_inspection_use_only_bounded_read_actions(settings, vienna):
    place = vienna.model_copy(update={"label": "London", "country_code": "GB"})

    def handler(request):
        if request.url.path.endswith("package_search"):
            assert request.url.params["rows"] == "3"
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {"results": [{"id": "synthetic-dataset", "title": "Income"}]},
                },
            )
        assert request.url.path.endswith("package_show")
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "title": "Income",
                    "notes": "Median only",
                    "license_id": "test-license",
                    "resources": [],
                },
            },
        )

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        proposals = await search_catalog(place, http)
        result = await inspect_source(proposals[0]["url"], http)
    assert result["format"] == "ckan" and result["fields"] == []


async def test_socrata_metadata_does_not_copy_rows(settings):
    async with SafeHTTP(
        settings,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "name": "Synthetic",
                    "columns": [{"fieldName": "area", "name": "Area code", "dataTypeName": "text"}],
                    "rows": [["never send rows"]],
                },
            )
        ),
        dns_check=allow_dns,
    ) as http:
        result = await inspect_source("https://data.sfgov.org/api/views/abcd-1234.json", http)
    assert result["format"] == "socrata" and "never send rows" not in json.dumps(result)
