import asyncio
from datetime import UTC, datetime

from ..config import Settings
from ..http import ProviderError, SafeHTTP
from ..models import (
    IncomeArea,
    IncomeBin,
    IncomeDefinition,
    NormalizedIncomeDataset,
    Place,
    SourceCandidate,
)

COUNTIES = ("005", "047", "061", "081", "085")
LIMITS = [
    None,
    10000,
    15000,
    20000,
    25000,
    30000,
    35000,
    40000,
    45000,
    50000,
    60000,
    75000,
    100000,
    125000,
    150000,
    200000,
    None,
]
LABELS = [
    "Less than $10,000",
    "$10,000 to $14,999",
    "$15,000 to $19,999",
    "$20,000 to $24,999",
    "$25,000 to $29,999",
    "$30,000 to $34,999",
    "$35,000 to $39,999",
    "$40,000 to $44,999",
    "$45,000 to $49,999",
    "$50,000 to $59,999",
    "$60,000 to $74,999",
    "$75,000 to $99,999",
    "$100,000 to $124,999",
    "$125,000 to $149,999",
    "$150,000 to $199,999",
    "$200,000 or more",
]
CENSUS_LICENSE = "https://www.census.gov/data/developers/about/terms-of-service.html"


def timestamp():
    return datetime.now(UTC).isoformat()


async def gather_cancel(*calls):
    """Unlike plain gather, cancel sibling downloads when one fails."""
    tasks = [asyncio.create_task(call) for call in calls]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class CensusNYCConnector:
    def __init__(self, http: SafeHTTP, settings: Settings):
        self.http, self.settings = http, settings
        self.layers = {}  # request scoped; metadata only
        self.state = "36"
        self.counties = COUNTIES
        self.extent_description = "New York City: documented union of five New York counties"

    async def get_extent(self, year: int) -> dict:
        return await self.get_boundaries(year, "Counties")

    def outline(self, extent: dict) -> dict:
        from ..geography.validation import city_outline

        return city_outline(
            extent, expected_count=len(self.counties), label=self.extent_description
        )

    def validate_geography(self, dataset, boundaries, extent):
        from ..geography.validation import join_and_validate

        return join_and_validate(
            dataset,
            boundaries,
            extent,
            expected_count=len(self.counties),
            extent_description=self.extent_description,
        )

    def supports(self, place: Place) -> tuple[float, str]:
        # Exact gazetteer identities, not a substring or a county pretending to be a city.
        known = (place.provider == "geonames" and place.provider_id == "5128581") or (
            place.provider == "photon" and place.provider_id in {"N:61785451", "R:175905"}
        )
        if (
            known
            and place.country_code == "US"
            and -74.3 < place.longitude < -73.6
            and 40.4 < place.latitude < 41
        ):
            return 1.0, "New York City: documented union of five New York counties"
        return 0.0, "No reviewed exact municipal tract footprint for this place"

    async def discover(self, place: Place, year: int) -> list[SourceCandidate]:
        base = f"https://api.census.gov/data/{year}/acs/acs5"
        group = await self.http.json(f"{base}/groups/B19001.json")
        variables = group.get("variables", {})
        for number in range(1, 18):
            for suffix in ("E", "M"):
                key = f"B19001_{number:03}{suffix}"
                if key not in variables or variables[key].get("predicateType") != "int":
                    raise ProviderError(
                        "income_schema",
                        "Official B19001 variables do not match the reviewed contract",
                    )
        for number, label in enumerate(LABELS, 2):
            if not variables[f"B19001_{number:03}E"].get("label", "").endswith(label):
                raise ProviderError(
                    "income_definition", "Official income bins changed; connector review required"
                )
        concept = variables["B19001_001E"].get("concept", "")
        if "HOUSEHOLD INCOME" not in concept.upper() or str(year) not in concept:
            raise ProviderError(
                "income_definition", "Household-income reference year could not be confirmed"
            )
        await self.layer(year, "Census Tracts")
        return [
            SourceCandidate(
                id="us_acs_b19001",
                publisher="U.S. Census Bureau",
                title=f"ACS {year - 4}–{year}, B19001: Household Income in the Past 12 Months",
                url=f"{base}/groups/B19001.html",
                year=year,
                geographic_unit="Census tract",
                income_concept=concept,
                geography_concept=f"{year} ACS census tracts; {self.extent_description}",
                license="U.S. federal public-domain data",
                license_url=CENSUS_LICENSE,
                permissions="public_domain",
                verified=True,
                retrieval_timestamp=timestamp(),
                citation=f"U.S. Census Bureau, {year} American Community Survey 5-Year Estimates, Table B19001.",
                limitations=[
                    "Five-year survey estimates, not a count of every household",
                    "90% margins of error are provided for each input; index uncertainty is not estimated",
                    "Non-equivalized income before taxes; no PPP adjustment",
                ],
            )
        ]

    async def layer(self, year: int, name: str) -> tuple[str, dict]:
        key = (year, name)
        if key in self.layers:
            return self.layers[key]
        base = f"https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS{year}/MapServer"
        service = await self.http.json(base, params={"f": "json"})
        matches = [x for x in service.get("layers", []) if x.get("name") == name]
        if len(matches) != 1:
            raise ProviderError(
                "geometry_vintage", "No unique matching ACS geography layer in official metadata"
            )
        url = f"{base}/{int(matches[0]['id'])}"
        metadata = await self.http.json(url, params={"f": "json"})
        fields = {x["name"] for x in metadata.get("fields", [])}
        if (
            not {"GEOID", "STATE", "COUNTY", "NAME"}.issubset(fields)
            or metadata.get("geometryType") != "esriGeometryPolygon"
        ):
            raise ProviderError(
                "geography_schema",
                "Official polygon layer has incompatible identifiers or geometry",
            )
        if not metadata.get("advancedQueryCapabilities", {}).get("supportsPagination"):
            raise ProviderError(
                "geography_pagination", "Official layer must support verified pagination"
            )
        self.layers[key] = (url, metadata)
        return url, metadata

    async def fetch(self, candidate: SourceCandidate, place: Place):
        api_key = self.settings.census_api_key.get_secret_value()
        if not api_key:
            raise ProviderError(
                "missing_census_key",
                "The operator must configure CENSUS_API_KEY for official ACS data queries",
            )
        variables = ["NAME"] + [f"B19001_{i:03}{s}" for i in range(1, 18) for s in ("E", "M")]
        return await gather_cancel(
            *(
                self.http.json(
                    f"https://api.census.gov/data/{candidate.year}/acs/acs5",
                    params={
                        "get": ",".join(variables),
                        "for": "tract:*",
                        "in": f"state:{self.state} county:{county}",
                        "key": api_key,
                    },
                )
                for county in self.counties
            )
        )

    def normalize(self, raw, candidate: SourceCandidate, place: Place) -> NormalizedIncomeDataset:
        if len(raw) != len(self.counties):
            raise ProviderError("income_coverage", "All verified footprint counties are required")
        areas, seen = [], set()
        for county, table in zip(self.counties, raw, strict=True):
            if not isinstance(table, list) or len(table) < 2 or not isinstance(table[0], list):
                raise ProviderError(
                    "income_schema", "ACS returned an empty or malformed county table"
                )
            headers = table[0]
            required = {"NAME", "state", "county", "tract"} | {
                f"B19001_{i:03}{s}" for i in range(1, 18) for s in ("E", "M")
            }
            if not required.issubset(headers) or len(set(headers)) != len(headers):
                raise ProviderError(
                    "income_schema", "ACS table is missing expected income variables"
                )
            for row in table[1:]:
                if not isinstance(row, list) or len(row) != len(headers):
                    raise ProviderError("income_schema", "Malformed ACS row")
                data = dict(zip(headers, row, strict=True))
                if (
                    data["state"] != self.state
                    or data["county"] != county
                    or not str(data["tract"]).isdigit()
                    or len(data["tract"]) != 6
                ):
                    raise ProviderError(
                        "wrong_geography",
                        "ACS geography does not match the verified city footprint",
                    )
                geoid = data["state"] + data["county"] + data["tract"]
                if geoid in seen:
                    raise ProviderError("duplicate_area", "Duplicate census tract identifiers")
                seen.add(geoid)
                estimates, moes = [], []
                for i in range(1, 18):
                    try:
                        estimate = int(data[f"B19001_{i:03}E"])
                    except (TypeError, ValueError) as exc:
                        raise ProviderError(
                            "suppressed_income",
                            "Missing or suppressed household estimates; no citywide index computed",
                        ) from exc
                    if estimate < 0:
                        raise ProviderError(
                            "suppressed_income",
                            "Negative/suppressed ACS estimates; no citywide index computed",
                        )
                    estimates.append(estimate)
                    try:
                        moe = int(data[f"B19001_{i:03}M"])
                    except (TypeError, ValueError):
                        moe = -1
                    moes.append(moe if moe >= 0 else None)
                if sum(estimates[1:]) != estimates[0]:
                    raise ProviderError(
                        "inconsistent_total",
                        "Income bands do not sum to the published household total",
                    )
                areas.append(
                    IncomeArea(
                        area_id=geoid,
                        name=data["NAME"],
                        parent_city=place.label,
                        total=estimates[0],
                        counts=estimates[1:],
                        margins_of_error=moes[1:],
                        total_margin_of_error=moes[0],
                        quality_flags=(["zero_households"] if estimates[0] == 0 else [])
                        + (["some_margins_of_error_unavailable"] if None in moes else []),
                    )
                )
        if len(areas) > self.settings.max_areas:
            raise ProviderError("area_limit", "City exceeds the configured area limit")
        year = candidate.year
        return NormalizedIncomeDataset(
            source=candidate,
            year=year,
            geometry_vintage=year,
            income=IncomeDefinition(
                price_basis=f"{year} inflation-adjusted USD; nominal domestic basis, not PPP",
                reference_period=f"{year - 4}–{year} ACS 5-year",
                bins=[
                    IncomeBin(
                        variable=f"B19001_{i + 2:03}E",
                        label=label,
                        lower=LIMITS[i],
                        upper=LIMITS[i + 1],
                    )
                    for i, label in enumerate(LABELS)
                ],
            ),
            areas=areas,
        )

    async def get_boundaries(self, year: int, layer_name: str = "Census Tracts") -> dict:
        url, metadata = await self.layer(year, layer_name)
        batch = min(250, int(metadata.get("maxRecordCount", 250)))
        if batch < 1:
            raise ProviderError("geography_schema", "Invalid provider record limit")

        async def county_features(county):
            where = f"STATE='{self.state}' AND COUNTY='{county}'"
            count = await self.http.json(
                f"{url}/query", params={"f": "json", "where": where, "returnCountOnly": "true"}
            )
            expected = count.get("count")
            if not isinstance(expected, int) or not 0 < expected <= self.settings.max_areas:
                raise ProviderError("geography_coverage", "Invalid official area count")
            result = []
            offset = 0
            while offset < expected:
                page = await self.http.json(
                    f"{url}/query",
                    params={
                        "f": "geojson",
                        "where": where,
                        "outFields": "GEOID,NAME,STATE,COUNTY",
                        "outSR": "4326",
                        "returnGeometry": "true",
                        "orderByFields": "GEOID ASC",
                        "resultOffset": offset,
                        "resultRecordCount": batch,
                    },
                )
                features = page.get("features")
                if (
                    page.get("type") != "FeatureCollection"
                    or not isinstance(features, list)
                    or not features
                    or len(features) > batch
                ):
                    raise ProviderError(
                        "geography_pagination", "Incomplete or malformed official geometry page"
                    )
                for feature in features:
                    p = feature.get("properties", {})
                    if p.get("STATE") != self.state or p.get("COUNTY") != county:
                        raise ProviderError(
                            "wrong_geography", "Boundary response includes an unexpected county"
                        )
                result.extend(features)
                offset += len(features)
                if len(result) > expected:
                    raise ProviderError(
                        "geography_pagination", "Geometry count changed during pagination"
                    )
            if len({f["properties"]["GEOID"] for f in result}) != expected:
                raise ProviderError(
                    "geography_pagination", "Duplicate or missing areas across boundary pages"
                )
            return result

        counties = await gather_cancel(*(county_features(county) for county in self.counties))
        features = [feature for county in counties for feature in county]
        if len(features) > self.settings.max_areas:
            raise ProviderError("area_limit", "Geometry area limit exceeded")
        return {
            "type": "FeatureCollection",
            "features": features,
            "provenance": {
                "publisher": "U.S. Census Bureau",
                "url": url,
                "year": year,
                "title": f"TIGERweb ACS {year} · {layer_name}",
                "retrieval_timestamp": timestamp(),
                "license": "U.S. federal public-domain data",
                "license_url": CENSUS_LICENSE,
            },
        }
