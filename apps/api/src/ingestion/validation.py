"""Deterministic trial of proposed field bindings on actual in-memory records."""

import math

from ..discovery.recipes import ConnectorRecipe
from .readers import ReadTable


def trial_mapping(table: ReadTable, recipe: ConnectorRecipe):
    issues, passed = [], []
    roles = {}
    for binding in recipe.bindings:
        roles.setdefault(binding.role, []).append(binding.field)
    identifiers, totals, bins = (
        roles.get("area_id", []),
        roles.get("total_households", []),
        roles.get("income_count", []),
    )
    if len(identifiers) != 1 or len(totals) != 1 or len(bins) < 2:
        return {
            "status": "invalid_data",
            "errors": [
                "Sélectionner un identifiant de zone, un total de ménages et au moins deux colonnes d’effectifs par tranche."
            ],
            "checks": [],
            "activation_allowed": False,
        }
    fields = identifiers + totals + bins
    if any(field not in table.fields for field in fields) or len(set(fields)) != len(fields):
        return {
            "status": "invalid_data",
            "errors": ["Les champs sélectionnés sont absents ou réutilisés dans plusieurs rôles."],
            "checks": [],
            "activation_allowed": False,
        }

    def count(value):
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, str):
            if not value.strip().isascii() or not value.strip().isdigit():
                raise ValueError
            value = int(value.strip())
        if (
            not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or value > 1e12
            or int(value) != value
        ):
            raise ValueError
        return int(value)

    seen, populated = set(), 0
    for row in table.rows:
        identifier = row[identifiers[0]]
        if (
            not isinstance(identifier, (str, int))
            or isinstance(identifier, bool)
            or not str(identifier).strip()
        ):
            issues.append("Un identifiant de zone est manquant.")
        elif str(identifier).strip() in seen:
            issues.append("Les identifiants de zone ne sont pas uniques.")
        seen.add(str(identifier).strip())
        try:
            total = count(row[totals[0]])
            values = [count(row[field]) for field in bins]
            if sum(values) != total:
                issues.append(
                    "La somme des tranches ne correspond pas au total publié ; vérifier les colonnes et l’exhaustivité des tranches."
                )
            populated += total > 0
        except (ValueError, TypeError, OverflowError):
            issues.append(
                "Un effectif est manquant, supprimé, négatif, non entier ou nécessite une convention numérique explicite."
            )
        if len(issues) > 10:
            break
    if len(table.rows) < 2 or populated < 2:
        issues.append("Au moins deux zones contenant des ménages sont nécessaires.")
    if not issues:
        passed = [
            "Identifiants uniques",
            "Effectifs entiers et non négatifs",
            "Totaux cohérents",
            "Plusieurs zones habitées",
        ]
    return {
        "status": "invalid_data" if issues else "data_checked",
        "errors": list(dict.fromkeys(issues)),
        "checks": passed,
        "activation_allowed": False,
        "missing": [
            "Définitions et ordre des tranches validés",
            "Droits de réutilisation",
            "Jointure géographique complète et périmètre de la ville",
        ],
    }
