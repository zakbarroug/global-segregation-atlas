"""SYNTHETIC protocol fixtures. Never imported by application code."""

import httpx

from src.connectors.census import COUNTIES, LABELS


def income_table(county):
    header = (
        ["NAME"]
        + [f"B19001_{i:03}{s}" for i in range(1, 18) for s in ("E", "M")]
        + ["state", "county", "tract"]
    )
    rows = []
    for index in range(2):
        counts = list(range(1, 17)) if index == 0 else list(range(16, 0, -1))
        values = [sum(counts), *counts]
        rows.append(
            [f"SYNTHETIC TRACT {index}"]
            + [str(v) for value in values for v in (value, 2)]
            + ["36", county, f"{index + 1:06}"]
        )
    return [header, *rows]


def polygon(x, y, width=0.01, height=0.01):
    return {
        "type": "Polygon",
        "coordinates": [[[x, y], [x + width, y], [x + width, y + height], [x, y + height], [x, y]]],
    }


def metadata():
    variables = {}
    for i in range(1, 18):
        for suffix in ("E", "M"):
            variables[f"B19001_{i:03}{suffix}"] = {
                "predicateType": "int",
                "concept": "HOUSEHOLD INCOME IN 2024",
                "label": "Total" if i == 1 else LABELS[i - 2],
            }
    return {"variables": variables}


def official_handler(request):
    path, query = request.url.path, request.url.params
    if request.url.host == "photon.komoot.io":
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-74.006, 40.713]},
                        "properties": {
                            "name": "New York",
                            "countrycode": "US",
                            "country": "United States",
                            "osm_type": "R",
                            "osm_id": 175905,
                            "osm_value": "city",
                        },
                    }
                ]
            },
        )
    if "statistik.at" in request.url.host or "hcp.ma" in request.url.host:
        return httpx.Response(
            200, text="<html>Synthetic official metadata page, no income table</html>"
        )
    if path.endswith("/groups/B19001.json"):
        return httpx.Response(200, json=metadata())
    if path.endswith("/acs/acs5"):
        return httpx.Response(200, json=income_table(query["in"].split("county:")[1]))
    if path.endswith("/MapServer"):
        # Deliberately different from live layer IDs: code must discover them.
        return httpx.Response(
            200,
            json={
                "layers": [{"id": 777, "name": "Census Tracts"}, {"id": 888, "name": "Counties"}]
            },
        )
    if path.endswith("/777") or path.endswith("/888"):
        return httpx.Response(
            200,
            json={
                "fields": [{"name": f} for f in ("GEOID", "NAME", "STATE", "COUNTY")],
                "geometryType": "esriGeometryPolygon",
                "maxRecordCount": 1,
                "advancedQueryCapabilities": {"supportsPagination": True},
            },
        )
    if path.endswith("/query"):
        county = query["where"].split("COUNTY='")[1][:3]
        county_index = COUNTIES.index(county)
        is_county = "/888/" in path
        if query.get("returnCountOnly") == "true":
            return httpx.Response(200, json={"count": 1 if is_county else 2})
        offset = int(query.get("resultOffset", 0))
        x, y = -74.0 + county_index * 0.03, 40.7
        geoid = "36" + county + ("" if is_county else f"{offset + 1:06}")
        geom = polygon(x, y, 0.02) if is_county else polygon(x + offset * 0.01, y)
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "GEOID": geoid,
                            "STATE": "36",
                            "COUNTY": county,
                            "NAME": "SYNTHETIC TEST AREA",
                        },
                        "geometry": geom,
                    }
                ],
            },
        )
    raise AssertionError(f"Unexpected test provider route: {request.url.host}{path}")
