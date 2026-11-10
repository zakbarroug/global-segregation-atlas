"""Declarative connector proposals. No model-generated executable code or data."""

import re
from typing import Literal

from pydantic import Field

from ..models import Contract


class FieldBinding(Contract):
    role: Literal["area_id", "area_name", "total_households", "income_count", "geometry"]
    field: str = Field(min_length=1, max_length=120)
    meaning: str = Field(min_length=1, max_length=300)


class ConnectorRecipe(Contract):
    version: Literal[1] = 1
    template: Literal[
        "census_acs_county_equivalent",
        "arcgis",
        "ckan",
        "socrata",
        "csv",
        "xlsx",
        "json",
        "geojson",
        "unsupported",
    ]
    source_url: str = Field(max_length=2000)
    title: str = Field(max_length=300)
    year: int | None = Field(ge=1900, le=2100)
    bindings: list[FieldBinding] = Field(max_length=80)
    evidence: list[str] = Field(max_length=12)
    missing: list[str] = Field(max_length=12)
    # Deliberately no license-grant, code, SQL, network-header or export-permission fields.


def check_recipe(recipe: ConnectorRecipe, inspection: dict) -> dict:
    """A model's claims cannot approve themselves. Bindings must exist in observed metadata."""
    errors = []
    fields = {f["name"] for f in inspection.get("fields", [])}
    if recipe.source_url != inspection["url"]:
        errors.append(
            "Recopier source_url exactement depuis metadata.url ; aucune autre source n’est autorisée."
        )
    if recipe.template != inspection["format"]:
        errors.append(
            f"Le template doit être exactement {inspection['format']!r}, le format du lecteur inspecté."
        )
    if len({b.field for b in recipe.bindings}) != len(recipe.bindings):
        errors.append("Un champ a été affecté plusieurs fois.")
    if any(b.field not in fields for b in recipe.bindings):
        errors.append("La proposition utilise des champs absents des métadonnées.")
    counts = [b for b in recipe.bindings if b.role == "income_count"]
    metadata = {f["name"]: f for f in inspection.get("fields", [])}
    for binding in counts:
        field = metadata.get(binding.field, {})
        label = field.get("label", "")
        if binding.field.upper() in {"HU100", "POP100", "AREALAND", "AREAWATER"} or re.search(
            r"\b(median|mean|average|percent|percentage|médian|moyen|population)\b", label, re.I
        ):
            errors.append(
                "Un champ de population, de superficie, de moyenne ou de pourcentage ne constitue pas un effectif de ménages par tranche de revenu."
            )
    blockers = []
    if len(counts) < 2:
        blockers.append(
            "Aucune distribution complète des ménages par tranches de revenus identifiée."
        )
    # This is a draft for a reviewed parser, never a route around scientific/license validation.
    return {
        "status": "rejected" if errors else "blocked" if blockers else "requires_review",
        "template": recipe.template,
        "recipe": recipe.model_dump(mode="json"),
        "checks": errors + blockers
        or ["Les champs proposés existent dans les métadonnées de la source."],
        "missing": list(
            dict.fromkeys(
                recipe.missing
                + [
                    "Définitions des ménages, des tranches et des revenus vérifiées",
                    "Droits de réutilisation et périmètre géographique vérifiés",
                    "Lecture complète des données et tests de jointure réussis",
                ]
            )
        ),
        "activated": False,
    }
