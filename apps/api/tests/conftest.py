"""All numeric fixtures in this directory are synthetic, FOR TESTS ONLY."""

import pytest

from src.config import Settings
from src.models import Place


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        app_env="test",
        census_api_key="test-not-a-real-key",
        geocoder="photon",
        place_token_secret="test-only-signing-secret",
        enable_ai_discovery=False,
    )


@pytest.fixture
def nyc():
    return Place(
        provider_id="R:175905",
        provider="photon",
        label="New York",
        country="United States",
        country_code="US",
        longitude=-74.006,
        latitude=40.713,
        source_url="https://www.openstreetmap.org/relation/175905",
    )


@pytest.fixture
def vienna():
    return Place(
        provider_id="R:109166",
        provider="photon",
        label="Vienne",
        country="Autriche",
        country_code="AT",
        longitude=16.37,
        latitude=48.21,
        source_url="https://www.openstreetmap.org/relation/109166",
    )
