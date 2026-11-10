import json

import httpx
import pytest
from fastapi.testclient import TestClient

from src.geography.places import PlaceTokens, search_places
from src.http import ProviderError, SafeHTTP
from src.main import create_app

from .provider_fixtures import official_handler
from .test_http import allow_dns


def mock_http(settings):
    return SafeHTTP(settings, transport=httpx.MockTransport(official_handler), dns_check=allow_dns)


def test_health_and_catalog_no_cache(settings):
    with TestClient(create_app(settings, mock_http)) as client:
        assert client.get("/health").json()["persistence"] == "none"
        response = client.get("/providers")
        assert response.json()["worldwide_measurement"] is False
        assert "no-store" in response.headers["cache-control"]


def test_search_and_ndjson_vertical_slice(settings):
    with TestClient(create_app(settings, mock_http)) as client:
        places = client.get("/places/search", params={"q": "New York"}).json()["places"]
        assert places[0]["country_code"] == "US"
        response = client.post(
            "/analysis",
            json={
                "city_id": places[0]["city_id"],
                "indices": ["dissimilarity", "isolation", "exposure", "theil_h"],
            },
        )
        events = [json.loads(line) for line in response.text.splitlines()]
        assert response.headers["content-type"].startswith("application/x-ndjson")
        assert events[-1] == {
            "event": "complete",
            "data": {
                "status": "measured",
                "message": "Analyse terminée ; données conservées uniquement dans cette session du navigateur",
            },
        }
        assert (
            len(next(e["data"]["geojson"]["features"] for e in events if e["event"] == "map_ready"))
            == 10
        )
        assert len([e for e in events if e["event"] == "metric_computed"]) == 4


def test_vienna_honest_fallback(settings, vienna):
    app = create_app(settings, mock_http)
    with TestClient(app) as client:
        response = client.post("/analysis", json={"city_id": app.state.tokens.encode(vienna)})
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[1]["event"] == "geography_ready"
        assert not any(e["event"] in ("map_ready", "metric_computed") for e in events)
        diagnostic = next(e["data"] for e in events if e["event"] == "insufficient_data")
        assert diagnostic["sources_attempted"][0]["status"] == "metadata_reachable"
        assert diagnostic["sources_attempted"][0]["dataset_verified"] is False


def test_missing_key_returns_explanation(settings, nyc):
    settings.census_api_key = ""
    # Re-validate to normalize the secret wrapper, as environment loading does.
    settings = type(settings).model_validate(settings.model_dump())
    app = create_app(settings, mock_http)
    with TestClient(app) as client:
        response = client.post("/analysis", json={"city_id": app.state.tokens.encode(nyc)})
        events = [json.loads(line) for line in response.text.splitlines()]
        assert any(e["data"].get("code") == "missing_census_key" for e in events)
        assert not any(e["event"] == "metric_computed" for e in events)


def test_bad_token_body_limit_and_search_throttle(settings):
    with TestClient(create_app(settings, mock_http)) as client:
        assert client.post("/analysis", json={"city_id": "forged-long-enough"}).status_code == 422
        assert client.post("/analysis", content=b"x" * 17000).status_code == 413
        assert client.get("/places/search?q=NY").status_code == 200
        assert client.get("/places/search?q=NY").status_code == 429


def test_signed_place_expiry_and_tamper(vienna, monkeypatch):
    tokens = PlaceTokens("synthetic-secret")
    token = tokens.encode(vienna)
    assert tokens.decode(token).label == "Vienne"
    with pytest.raises(ProviderError):
        tokens.decode(token[:-1] + ("1" if token[-1] != "1" else "2"))
    monkeypatch.setattr("src.geography.places.time.time", lambda: 9999999999)
    with pytest.raises(ProviderError):
        tokens.decode(token)


async def test_geonames_diacritics_disambiguation(settings):
    settings.geocoder = "geonames"
    settings.geonames_username = "test"

    def handler(request):
        assert request.url.params["q"] == "Vienne"
        return httpx.Response(
            200,
            json={
                "geonames": [
                    {
                        "geonameId": 1,
                        "name": "Vienne",
                        "toponymName": "Wien",
                        "countryName": "Autriche",
                        "countryCode": "AT",
                        "lng": 16.37,
                        "lat": 48.21,
                        "adminName1": "Wien",
                        "alternateNames": [{"name": "Vienna"}],
                    },
                    {
                        "geonameId": 2,
                        "name": "Vienne",
                        "toponymName": "Vienne",
                        "countryName": "France",
                        "countryCode": "FR",
                        "lng": 4.87,
                        "lat": 45.52,
                        "adminName1": "Auvergne-Rhône-Alpes",
                    },
                ]
            },
        )

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        places = await search_places("Vienne", http, settings, PlaceTokens("test"))
        assert [p.country_code for p in places] == ["AT", "FR"]
        assert places[0].alternate_names == ["Vienna"]
