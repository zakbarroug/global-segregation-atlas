"""Generic file readers with explicit parser choices and strict size/shape checks."""

import csv
import io
import json
import math
from dataclasses import dataclass
from typing import Any, Literal
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from pydantic import Field

from ..http import ProviderError
from ..models import Contract


class ReaderSpec(Contract):
    format: Literal["csv", "xlsx", "json", "geojson"]
    encoding: Literal["utf-8-sig", "utf-8", "cp1252"] = "utf-8-sig"
    delimiter: Literal[",", ";", "\t", "|"] = ","
    sheet: str | None = Field(default=None, max_length=100)
    header_row: int = Field(default=1, ge=1, le=25)
    table_path: list[str] = Field(default_factory=list, max_length=4)


@dataclass
class ReadTable:
    fields: list[str]
    rows: list[dict[str, Any]]
    geometries: list[dict | None]
    format: str
    hints: dict

    def close(self):
        self.rows.clear()
        self.geometries.clear()

    def metadata(self):
        """Schema/types only: no sample rows, values, geometries or statistics."""
        fields = []
        for name in self.fields:
            types = {
                type(row[name]).__name__ for row in self.rows[:100] if row.get(name) is not None
            }
            fields.append(
                {"name": name, "label": name, "type": "/".join(sorted(types)) or "unknown"}
            )
        return {"fields": fields, "format": self.format, "row_count": len(self.rows), **self.hints}


def fail(code, message):
    raise ProviderError(code, message)


def headers(values):
    if not values or len(values) > 200:
        fail("table_columns", "Le tableau doit contenir entre 1 et 200 colonnes.")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 120 for v in values):
        fail("table_header", "En-tête absent ou ambigu ; choisir la feuille et la ligne d’en-tête.")
    result = [v.strip() for v in values]
    if len(set(result)) != len(result):
        fail("table_header", "Noms de colonnes dupliqués après normalisation des espaces.")
    return result


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("table_json", "Clé JSON dupliquée ; lecture refusée.")
        result[key] = value
    return result


def read_table(raw: bytes, spec: ReaderSpec, settings) -> ReadTable:
    if len(raw) > min(settings.max_download_bytes, 10_000_000):
        fail("table_bytes", "Le fichier dépasse le budget de lecture de 10 Mo.")
    rows, geoms = [], []
    fields = []
    hints = {}

    def append(values, geometry=None):
        if (
            len(rows) >= settings.max_table_rows
            or (len(rows) + 1) * len(fields) > settings.max_table_cells
        ):
            fail(
                "table_rows",
                "Le tableau dépasse le budget de lignes/cellules ; aucune lecture partielle n’est validée.",
            )
        if len(values) != len(fields):
            fail(
                "table_shape", "Une ligne ne possède pas le même nombre de colonnes que l’en-tête."
            )
        for value in values:
            if isinstance(value, (dict, list, tuple)):
                fail(
                    "table_shape",
                    "Une cellule contient une structure imbriquée non prise en charge.",
                )
            if isinstance(value, float) and not math.isfinite(value):
                fail("table_number", "Valeur numérique non finie.")
            if isinstance(value, str) and len(value) > 5000:
                fail("table_cell", "Une cellule dépasse la taille maximale.")
        rows.append(dict(zip(fields, values, strict=True)))
        geoms.append(geometry)

    try:
        if spec.format == "csv":
            text = raw.decode(spec.encoding)
            iterator = csv.reader(
                io.StringIO(text, newline=""), delimiter=spec.delimiter, strict=True
            )
            for _ in range(spec.header_row - 1):
                next(iterator)
            fields = headers(next(iterator))
            for row in iterator:
                if row:  # Empty physical lines carry no observations.
                    append(row)
        elif spec.format == "xlsx":
            from openpyxl import load_workbook

            with ZipFile(io.BytesIO(raw)) as archive:
                members = archive.infolist()
                if len(members) > 1000 or sum(m.file_size for m in members) > 30_000_000:
                    fail("workbook_limit", "Classeur décompressé trop volumineux.")
                if any(
                    m.flag_bits & 1 or m.file_size > max(1, m.compress_size) * 200 for m in members
                ):
                    fail("workbook_limit", "Classeur chiffré ou compression excessive.")
                if any(
                    "vbaproject" in m.filename.lower() or "externallinks/" in m.filename.lower()
                    for m in members
                ):
                    fail(
                        "workbook_active_content",
                        "Les macros et les liens externes ne sont pas acceptés.",
                    )
            workbook = load_workbook(
                io.BytesIO(raw), read_only=True, data_only=False, keep_links=False
            )
            try:
                hints["sheets"] = workbook.sheetnames[:20]
                if spec.sheet is None and len(workbook.sheetnames) != 1:
                    fail(
                        "workbook_sheet",
                        "Plusieurs feuilles : sélectionner explicitement une feuille.",
                    )
                if spec.sheet is not None and spec.sheet not in workbook.sheetnames:
                    fail("workbook_sheet", "La feuille demandée n’existe pas.")
                sheet = workbook[spec.sheet or workbook.sheetnames[0]]
                if (sheet.max_column or 0) > 200 or (
                    sheet.max_row or 0
                ) > settings.max_table_rows + spec.header_row:
                    fail("workbook_limit", "Dimensions du classeur au-delà du budget.")
                iterator = sheet.iter_rows(min_row=spec.header_row)
                fields = headers([c.value for c in next(iterator)])
                for cells in iterator:
                    if any(c.data_type == "f" for c in cells):
                        fail(
                            "workbook_formula",
                            "Les formules exigent une source de valeurs officielles ; aucune formule n’est exécutée.",
                        )
                    if any(c.value is not None for c in cells):
                        append([c.value for c in cells])
            finally:
                workbook.close()
        else:
            data = json.loads(raw, object_pairs_hook=object_pairs)
            for key in spec.table_path:
                if not isinstance(data, dict) or key not in data:
                    fail(
                        "table_path",
                        "Chemin JSON absent ; seuls les noms de clés explicites sont acceptés.",
                    )
                data = data[key]
            if spec.format == "geojson":
                if (
                    not isinstance(data, dict)
                    or data.get("type") != "FeatureCollection"
                    or data.get("crs")
                ):
                    fail(
                        "geojson_schema",
                        "Une FeatureCollection GeoJSON RFC 7946 sans CRS alternatif est requise.",
                    )
                features = data.get("features")
                if not isinstance(features, list) or not features:
                    fail("geojson_schema", "La source ne contient pas de polygones.")
                if not isinstance(features[0], dict) or not isinstance(
                    features[0].get("properties"), dict
                ):
                    fail("geojson_schema", "Propriétés GeoJSON absentes ou invalides.")
                fields = headers(list(features[0]["properties"]))
                from ..geography.validation import checked_polygon

                for feature in features:
                    if not isinstance(feature, dict) or not isinstance(
                        feature.get("properties"), dict
                    ):
                        fail("geojson_schema", "Objet GeoJSON invalide.")
                    props = feature.get("properties", {})
                    if feature.get("type") != "Feature" or set(props) != set(fields):
                        fail("table_shape", "Propriétés GeoJSON incohérentes.")
                    checked_polygon(feature.get("geometry"))
                    append([props[k] for k in fields], feature["geometry"])
            else:
                if not isinstance(data, list) or not data:
                    fail("table_json", "Un tableau JSON non vide est requis.")
                if isinstance(data[0], list):
                    fields = headers(data[0])
                    for row in data[1:]:
                        if not isinstance(row, list):
                            fail("table_shape", "Lignes JSON incompatibles.")
                        append(row)
                elif isinstance(data[0], dict):
                    fields = headers(list(data[0]))
                    for row in data:
                        if not isinstance(row, dict) or set(row) != set(fields):
                            fail("table_shape", "Clés JSON différentes selon les lignes.")
                        append([row[k] for k in fields])
                else:
                    fail("table_json", "Format JSON non tabulaire.")
        if not rows:
            fail("table_empty", "Le fichier ne contient aucune observation.")
        return ReadTable(fields, rows, geoms, spec.format, hints)
    except ProviderError:
        rows.clear()
        geoms.clear()
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        UnicodeError,
        csv.Error,
        BadZipFile,
        StopIteration,
        RecursionError,
        DefusedXmlException,
    ) as exc:
        rows.clear()
        geoms.clear()
        raise ProviderError(
            "table_parse", "Le lecteur n’a pas pu interpréter le fichier avec ces paramètres."
        ) from exc
