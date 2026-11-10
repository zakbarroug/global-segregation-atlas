from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Place(Contract):
    city_id: str = ""
    provider_id: str
    provider: str
    label: str
    country: str
    country_code: str = Field(min_length=2, max_length=2)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    admin_labels: list[str] = []
    admin_codes: dict[str, str] = {}
    alternate_names: list[str] = []
    extent_provenance: str = "Gazetteer point; no verified municipal boundary"
    source_url: HttpUrl


class SourceCandidate(Contract):
    id: str
    publisher: str
    title: str
    url: HttpUrl
    year: int | None = None
    geographic_unit: str
    income_concept: str
    geography_concept: str
    license: str
    license_url: HttpUrl
    citation: str
    access_method: str = "HTTPS JSON API"
    permissions: Literal["public_domain", "metadata_only", "unverified"]
    limitations: list[str] = []
    verified: bool = False
    retrieval_timestamp: str | None = None


class IncomeBin(Contract):
    variable: str
    label: str
    lower: float | None
    upper: float | None


class IncomeDefinition(Contract):
    unit: Literal["households"] = "households"
    concept: str = "Household money income before taxes"
    currency: str = "USD"
    period: str = "Annual; income in the past 12 months"
    equivalized: bool = False
    price_basis: str
    reference_period: str
    bins: list[IncomeBin]
    low_group: str = "Less than $35,000 (B19001_002E–007E)"
    high_group: str = "$100,000 or more (B19001_014E–017E)"
    middle_group: str = (
        "$35,000–99,999; excluded from D but retained in isolation/exposure denominators"
    )


class IncomeArea(Contract):
    area_id: str
    name: str
    parent_city: str
    total: int = Field(ge=0)
    counts: list[int]
    margins_of_error: list[int | None]
    total_margin_of_error: int | None
    quality_flags: list[str] = []


class NormalizedIncomeDataset(Contract):
    source: SourceCandidate
    income: IncomeDefinition
    year: int
    geometry_vintage: int
    areas: list[IncomeArea]


class GeographicUnit(Contract):
    area_id: str
    name: str
    parent_city: str
    geometry: dict[str, Any]
    geometry_vintage: int
    households: int = Field(ge=0)
    quality_flags: list[str] = []


class DisplayArea(GeographicUnit):
    low_households: int = Field(ge=0)
    high_households: int = Field(ge=0)
    low_share: float | None = Field(ge=0, le=1)
    high_share: float | None = Field(ge=0, le=1)
    income_counts: list[int]
    income_moe_90: list[int | None]
    total_moe_90: int | None


class Metric(Contract):
    id: str
    label: str
    value: float | None
    definition: str
    interpretation: str
    target_groups: str
    unavailable_reason: str | None = None
    warnings: list[str] = []
    input_coverage: dict[str, int | float | str] = {}


class AnalysisRequest(Contract):
    city_id: str = Field(min_length=10, max_length=6000)
    requested_year: int | None = Field(default=None, ge=2020, le=2030)
    indices: (
        list[Literal["dissimilarity", "isolation", "exposure", "theil_h", "rank_order_h"]] | None
    ) = Field(default=None, max_length=5)


class Event(Contract):
    event: Literal[
        "started",
        "geography_ready",
        "source_found",
        "discovery_progress",
        "downloading",
        "validating",
        "metric_computed",
        "map_ready",
        "insufficient_data",
        "failed",
        "complete",
    ]
    data: dict[str, Any]
