from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[3] / ".env")
        if len(Path(__file__).resolve().parents) > 3
        else ".env",
        extra="ignore",
    )
    app_env: Literal["development", "production", "test"] = "development"
    census_api_key: SecretStr = SecretStr("")
    geonames_username: str = ""
    geocoder: Literal["photon", "geonames"] = "photon"
    place_token_secret: SecretStr = SecretStr("")
    acs_year: int = Field(default=2024, ge=2020, le=2030)
    http_timeout_seconds: float = Field(default=25, gt=0, le=60)
    analysis_timeout_seconds: float = Field(default=180, gt=0, le=600)
    max_concurrent_analyses: int = Field(default=2, ge=1, le=8)
    max_download_bytes: int = Field(default=25_000_000, ge=1000, le=50_000_000)
    max_request_download_bytes: int = Field(default=120_000_000, ge=1000, le=250_000_000)
    max_response_bytes: int = Field(default=16_000_000, ge=1000, le=25_000_000)
    max_areas: int = Field(default=10000, ge=2, le=20000)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    enable_ai_discovery: bool = False
    openai_api_key: SecretStr = SecretStr("")
    openai_discovery_model: str = "gpt-4.1-mini"
    ai_provider: Literal["openai", "compatible"] = "openai"
    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: SecretStr = SecretStr("")
    ai_allow_local: bool = False
    ai_free_only: bool = True
    searxng_url: str = ""
    web_search_provider: Literal["searxng", "tavily"] = "searxng"
    tavily_api_key: SecretStr = SecretStr("")
    tavily_free_only: bool = True
    search_allow_local: bool = False
    web_discovery_enabled: bool = False
    discovery_max_pages: int = Field(default=8, ge=1, le=15)
    discovery_max_searches: int = Field(default=3, ge=1, le=5)
    discovery_max_steps: int = Field(default=6, ge=2, le=10)
    discovery_timeout_seconds: float = Field(default=90, ge=15, le=150)
    max_table_rows: int = Field(default=20000, ge=2, le=100000)
    max_table_cells: int = Field(default=1000000, ge=100, le=2000000)

    @model_validator(mode="after")
    def production_configuration(self):
        if self.app_env == "production":
            if self.geocoder != "geonames" or not self.geonames_username:
                raise ValueError("Production requires a configured GeoNames account and quota plan")
            if len(self.place_token_secret.get_secret_value()) < 32:
                raise ValueError("Production requires PLACE_TOKEN_SECRET of at least 32 characters")
        return self
