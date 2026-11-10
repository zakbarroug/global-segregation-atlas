import numpy as np
from pyproj import Transformer
from shapely import STRtree, transform
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from ..http import ProviderError
from ..models import DisplayArea, NormalizedIncomeDataset

TO_METERS = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform
TO_LONLAT = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True).transform


def checked_polygon(geometry):
    try:
        geom = shape(geometry)
        if geom.geom_type not in ("Polygon", "MultiPolygon") or geom.is_empty or not geom.is_valid:
            raise ValueError
        bounds = np.asarray(geom.bounds)
        if not np.isfinite(bounds).all() or not (
            -180 <= bounds[0] <= bounds[2] <= 180 and -90 <= bounds[1] <= bounds[3] <= 90
        ):
            raise ValueError
        return geom
    except (ValueError, TypeError, KeyError) as exc:
        raise ProviderError(
            "invalid_geometry", "Invalid polygon, topology or longitude/latitude CRS"
        ) from exc


def city_outline(
    counties: dict, *, expected_count=5, label="New York City · five-county footprint"
) -> dict:
    if len(counties["features"]) != expected_count:
        raise ProviderError(
            "city_extent", "The footprint must contain exactly the verified official counties"
        )
    union = unary_union([checked_polygon(f["geometry"]) for f in counties["features"]])
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": label,
                    "extent_type": "verified_county_union",
                },
                "geometry": mapping(union),
            }
        ],
    }


def join_and_validate(
    dataset: NormalizedIncomeDataset,
    polygons: dict,
    counties: dict,
    *,
    expected_count=5,
    extent_description="New York City · cinq comtés",
) -> tuple[dict, dict, list[str]]:
    if (
        dataset.year != dataset.geometry_vintage
        or polygons["provenance"]["year"] != dataset.year
        or counties["provenance"]["year"] != dataset.year
    ):
        raise ProviderError(
            "vintage_mismatch", "Income and boundaries must use the same ACS vintage"
        )
    source_features = polygons["features"]
    boundaries = {f["properties"]["GEOID"]: f for f in source_features}
    areas = {a.area_id: a for a in dataset.areas}
    if len(boundaries) != len(source_features) or len(areas) != len(dataset.areas):
        raise ProviderError("duplicate_area", "Duplicate income or boundary area identifiers")
    if areas.keys() != boundaries.keys():
        raise ProviderError(
            "join_coverage",
            f"Exact join failed: {len(areas.keys() - boundaries.keys())} income areas lack polygons; {len(boundaries.keys() - areas.keys())} polygons lack income. No partial-city index computed.",
        )
    footprint = transform(
        shape(
            city_outline(counties, expected_count=expected_count, label=extent_description)[
                "features"
            ][0]["geometry"]
        ),
        TO_METERS,
        interleaved=False,
    )
    geometries = [
        transform(checked_polygon(boundaries[key]["geometry"]), TO_METERS, interleaved=False)
        for key in areas
    ]
    for geom in geometries:
        # Geometry tolerances are geometric only; never interpolate household counts.
        if geom.area <= 0 or geom.difference(footprint.buffer(2)).area > max(5, geom.area * 1e-6):
            raise ProviderError(
                "city_extent", "Tracts extend outside the verified municipal footprint"
            )
    tree = STRtree(geometries)
    for index, geom in enumerate(geometries):
        for other in tree.query(geom, predicate="intersects"):
            if other > index and geom.intersection(geometries[other]).area > max(
                2, min(geom.area, geometries[other].area) * 1e-7
            ):
                raise ProviderError(
                    "overlapping_areas",
                    "Small-area interiors overlap; segregation geography is invalid",
                )
    features = []
    for (key, area), geom in zip(areas.items(), geometries, strict=True):
        simple = transform(geom.simplify(15, preserve_topology=True), TO_LONLAT, interleaved=False)
        low, high = sum(area.counts[:6]), sum(area.counts[12:])
        display = DisplayArea(
            area_id=key,
            name=area.name,
            parent_city=area.parent_city,
            geometry=mapping(simple),
            geometry_vintage=dataset.geometry_vintage,
            households=area.total,
            low_households=low,
            high_households=high,
            low_share=low / area.total if area.total else None,
            high_share=high / area.total if area.total else None,
            income_counts=area.counts,
            income_moe_90=area.margins_of_error,
            total_moe_90=area.total_margin_of_error,
            quality_flags=area.quality_flags,
        )
        features.append(
            {
                "type": "Feature",
                "id": key,
                "geometry": display.geometry,
                "properties": display.model_dump(exclude={"geometry"}),
            }
        )
    warnings = [
        f"Géographie vérifiée : {extent_description}. Ne représente pas l’aire métropolitaine.",
        "Estimations d’enquête ACS sur cinq ans ; marges d’erreur à 90 % disponibles pour les effectifs, pas pour les indices.",
        "Les résultats dépendent du découpage en census tracts (effet de zonage / MAUP).",
        "Polygones d’affichage simplifiés à 15 m en projection EPSG:5070 ; aucun ménage réaffecté. De minces écarts visuels peuvent apparaître aux limites.",
        "Revenu des ménages avant impôts, non équivalisé. Comparaisons internationales directes non justifiées.",
    ]
    empty = sum(a.total == 0 for a in areas.values())
    if empty:
        warnings.append(
            f"{empty} secteurs sans ménage : inclus dans la couverture, sans valeur de couleur."
        )
    if any(None in a.margins_of_error or a.total_margin_of_error is None for a in areas.values()):
        warnings.append("Certaines marges d’erreur sont indisponibles ou supprimées par le Census.")
    coverage = {
        "areas": len(areas),
        "populated_areas": len(areas) - empty,
        "households": sum(a.total for a in areas.values()),
        "income_areas_matched": len(areas),
        "boundary_areas_matched": len(boundaries),
        "fraction": 1.0,
    }
    return {"type": "FeatureCollection", "features": features}, coverage, warnings
