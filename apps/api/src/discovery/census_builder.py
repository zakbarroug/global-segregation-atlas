"""Build an ACS connector from a live, exact municipal/county equivalence proof.

The recipe is generated from official ArcGIS metadata, independently of an LLM.
All geometry/data remain request scoped; no city lookup table is populated.
"""

import re
import unicodedata

from shapely.geometry import Point

from ..connectors.census import CENSUS_LICENSE, CensusNYCConnector, timestamp
from ..geography.validation import checked_polygon
from ..http import ProviderError


def normalized_name(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if c.isalnum())


class CensusEquivalentConnector(CensusNYCConnector):
    def __init__(self, http, settings, state, county, label, extent):
        super().__init__(http, settings)
        self.state, self.counties = state, (county,)
        self.extent_description = f"{label} : commune et comté de limites officielles identiques"
        self.verified_extent = extent

    async def get_extent(self, year):
        if self.verified_extent["provenance"]["year"] != year:
            raise ProviderError("vintage_mismatch", "Municipal proof and request years differ")
        return self.verified_extent


async def build_census_connector(place, year, http, settings):
    if place.country_code != "US":
        return None, None
    base = f"https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS{year}/MapServer"
    service = await http.json(base, params={"f": "json"})

    async def locate(name):
        layers = [layer for layer in service.get("layers", []) if layer.get("name") == name]
        if len(layers) != 1:
            raise ProviderError("builder_layer", "La couche officielle de limites est ambiguë.")
        url = f"{base}/{int(layers[0]['id'])}"
        metadata = await http.json(url, params={"f": "json"})
        fields = {f["name"] for f in metadata.get("fields", [])}
        expected = {
            "GEOID",
            "NAME",
            "BASENAME",
            "STATE",
            "COUNTY" if name == "Counties" else "PLACE",
        }
        if not expected <= fields or metadata.get("geometryType") != "esriGeometryPolygon":
            raise ProviderError("builder_schema", "Métadonnées géographiques incompatibles.")
        response = await http.json(
            f"{url}/query",
            params={
                "f": "geojson",
                "geometry": f"{place.longitude},{place.latitude}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": ",".join(sorted(expected)),
                "outSR": "4326",
                "returnGeometry": "true",
                "resultRecordCount": 3,
            },
        )
        if response.get("type") != "FeatureCollection" or response.get("exceededTransferLimit"):
            raise ProviderError("builder_geometry", "Réponse géographique incomplète.")
        features = response.get("features", [])
        if len(features) != 1:
            raise ProviderError("builder_extent", "Aucune limite municipale unique pour ce point.")
        feature = features[0]
        geom = checked_polygon(feature.get("geometry"))
        if not geom.covers(Point(place.longitude, place.latitude)):
            raise ProviderError(
                "builder_extent", "La limite officielle ne contient pas la ville sélectionnée."
            )
        return url, feature, geom

    from ..connectors.census import gather_cancel

    municipal, county = await gather_cancel(locate("Incorporated Places"), locate("Counties"))
    municipal_url, municipal_feature, municipal_geom = municipal
    county_url, county_feature, county_geom = county
    props, county_props = municipal_feature["properties"], county_feature["properties"]
    names = {normalized_name(n) for n in [place.label, *place.alternate_names]}
    if normalized_name(props.get("BASENAME", "")) not in names:
        raise ProviderError(
            "builder_identity", "Le nom officiel ne correspond pas à la ville sélectionnée."
        )
    state, county_code = props.get("STATE", ""), county_props.get("COUNTY", "")
    if (
        not re.fullmatch(r"\d{2}", state)
        or not re.fullmatch(r"\d{3}", county_code)
        or county_props.get("STATE") != state
        or county_props.get("GEOID") != state + county_code
        or not re.fullmatch(state + r"\d{5}", props.get("GEOID", ""))
    ):
        raise ProviderError("builder_identifiers", "Identifiants Census incohérents.")
    if state in {"02", "15"} or int(state) > 56:
        raise ProviderError(
            "builder_projection", "Cette région nécessite une projection géométrique adaptée."
        )
    # Exact topological equality: never replace a city by its surrounding county,
    # clip observations, infer allocation, or silently admit a partial-city score.
    if not municipal_geom.equals(county_geom):
        raise ProviderError(
            "builder_extent",
            "La commune et le comté ont des limites différentes ; une sélection exacte des petites zones reste nécessaire.",
        )
    extent = {
        "type": "FeatureCollection",
        "features": [county_feature],
        "provenance": {
            "publisher": "U.S. Census Bureau",
            "url": county_url,
            "year": year,
            "title": f"TIGERweb ACS {year} · municipal/county equivalence",
            "retrieval_timestamp": timestamp(),
            "license": "U.S. federal public-domain data",
            "license_url": CENSUS_LICENSE,
            "municipal_boundary_url": municipal_url,
            "municipal_geoid": props["GEOID"],
            "equivalence": "exact_topological_equality",
        },
    }
    connector = CensusEquivalentConnector(http, settings, state, county_code, place.label, extent)
    report = {
        "status": "configured",
        "template": "census_acs_county_equivalent",
        "activated": True,
        "message": "Connecteur ACS configuré automatiquement ; les données seront ensuite intégralement validées.",
        "recipe": {
            "version": 1,
            "template": "census_acs_county_equivalent",
            "year": year,
            "state": state,
            "counties": [county_code],
            "municipal_geoid": props["GEOID"],
            "income_table": "B19001",
            "income_source": f"https://api.census.gov/data/{year}/acs/acs5",
            "geometry_source": base,
        },
        "checks": [
            "Identité de la commune",
            "Millésime des limites",
            "Égalité exacte commune/comté",
        ],
        "missing": [],
    }
    return connector, report
