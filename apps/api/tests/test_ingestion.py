"""Synthetic files only. No observations written to disk, including XLSX fixtures."""

import io
import json

import httpx
import pytest
from openpyxl import Workbook

from src.discovery.planner import ConnectorPlanningAgent
from src.discovery.recipes import ConnectorRecipe
from src.http import ProviderError, SafeHTTP
from src.ingestion.probe import probe_table
from src.ingestion.readers import ReaderSpec, read_table
from src.ingestion.validation import trial_mapping

from .test_http import allow_dns


def recipe():
    return ConnectorRecipe.model_validate(
        {
            "template": "csv",
            "source_url": "https://api.census.gov/synthetic",
            "title": "Synthetic",
            "year": 2024,
            "evidence": [],
            "missing": [],
            "bindings": [
                {"role": role, "field": field, "meaning": "Synthetic test field"}
                for role, field in [
                    ("area_id", "id"),
                    ("total_households", "total"),
                    ("income_count", "low"),
                    ("income_count", "high"),
                ]
            ],
        }
    )


def xlsx(rows, *, multiple=False):
    book = Workbook()
    for row in rows:
        book.active.append(row)
    if multiple:
        book.create_sheet("Second")
    buffer = io.BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


@pytest.mark.parametrize("format", ["csv", "xlsx", "json", "geojson"])
def test_readers_preserve_identifiers_and_never_include_values_in_metadata(settings, format):
    rows = [
        {"id": "001", "total": 10, "low": 4, "high": 6},
        {"id": "002", "total": 10, "low": 7, "high": 3},
    ]
    if format == "csv":
        raw = b"id,total,low,high\r\n001,10,4,6\r\n002,10,7,3\r\n"
    elif format == "xlsx":
        raw = xlsx([list(rows[0]), *[list(row.values()) for row in rows]])
    elif format == "geojson":
        raw = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": row,
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                        },
                    }
                    for row in rows
                ],
            }
        ).encode()
    else:
        raw = json.dumps(rows).encode()
    table = read_table(raw, ReaderSpec(format=format), settings)
    assert table.rows[0]["id"] == "001"
    assert "001" not in json.dumps(table.metadata()) and "coordinates" not in json.dumps(
        table.metadata()
    )
    report = trial_mapping(table, recipe())
    assert report["status"] == "data_checked" and report["activation_allowed"] is False
    table.close()
    assert not table.rows and not table.geometries


@pytest.mark.parametrize(
    "raw,format,code",
    [
        (b"a,a\n1,2", "csv", "table_header"),
        (b"a,b\n1,2,3", "csv", "table_shape"),
        (b"a\n", "csv", "table_empty"),
        (b'[{"a": 1, "a":2}]', "json", "table_json"),
        (b'[{"a":1},{"b":2}]', "json", "table_shape"),
        (b'[{"a":NaN}]', "json", "table_number"),
        (b'[{"a":{"b":1}}]', "json", "table_shape"),
        (b'{"type":"FeatureCollection","features":[null]}', "geojson", "geojson_schema"),
        (
            b'{"type":"FeatureCollection","crs":"EPSG:3857","features":[]}',
            "geojson",
            "geojson_schema",
        ),
    ],
)
def test_malformed_files_cannot_silently_become_valid_tables(settings, raw, format, code):
    with pytest.raises(ProviderError) as exc:
        read_table(raw, ReaderSpec(format=format), settings)
    assert exc.value.code == code


def test_csv_explicit_local_conventions_and_json_path(settings):
    table = read_table(
        "titre\r\ncode;nom\r\n001;Ménages".encode("cp1252"),
        ReaderSpec(format="csv", delimiter=";", encoding="cp1252", header_row=2),
        settings,
    )
    assert table.rows == [{"code": "001", "nom": "Ménages"}]
    nested = read_table(
        b'{"result":{"rows":[["id"],["001"]]}}',
        ReaderSpec(format="json", table_path=["result", "rows"]),
        settings,
    )
    assert nested.rows == [{"id": "001"}]


def test_complete_file_required_and_xlsx_never_evaluates_formulas(settings):
    settings.max_table_rows = 2
    with pytest.raises(ProviderError, match="aucune lecture partielle"):
        read_table(b"id\n1\n2\n3", ReaderSpec(format="csv"), settings)
    for raw, code in [
        (xlsx([["id"], ["=1+1"]]), "workbook_formula"),
        (xlsx([["id"], ["001"]], multiple=True), "workbook_sheet"),
    ]:
        with pytest.raises(ProviderError) as exc:
            read_table(raw, ReaderSpec(format="xlsx"), settings)
        assert exc.value.code == code


@pytest.mark.parametrize("bad", ["-1", "1.2", "1,000", "..", "NaN", "", "9"])
def test_bad_or_incomplete_counts_cannot_pass(settings, bad):
    table = read_table(
        f'id,total,low,high\na,10,"{bad}",6\nb,10,7,3'.encode(), ReaderSpec(format="csv"), settings
    )
    assert trial_mapping(table, recipe())["status"] == "invalid_data"


def test_duplicate_identifiers_and_missing_bindings_rejected(settings):
    table = read_table(b"id,total,low,high\na,10,4,6\na,10,7,3", ReaderSpec(format="csv"), settings)
    assert trial_mapping(table, recipe())["status"] == "invalid_data"
    missing = recipe().model_copy(update={"bindings": recipe().bindings[:-1]})
    assert trial_mapping(table, missing)["status"] == "invalid_data"


async def test_real_row_checks_drive_one_model_repair_without_observation_disclosure(
    settings, vienna
):
    settings.enable_ai_discovery = True
    settings.openai_api_key = type(settings.openai_api_key)("synthetic-key")
    table = read_table(
        b"id,total,low,high,irrelevant\nSECRET_AREA_1,10,4,6,0\nSECRET_AREA_2,10,7,3,0",
        ReaderSpec(format="csv"),
        settings,
    )
    calls = []

    def handler(request):
        body = json.loads(request.content)
        assert "SECRET_AREA" not in request.content.decode()
        calls.append(body)
        proposed = recipe().model_dump()
        if len(calls) == 1:
            proposed["bindings"][-1]["field"] = "irrelevant"
        else:
            assert any(message["role"] == "assistant" for message in body["input"])
            assert "somme des tranches" in json.dumps(body["input"], ensure_ascii=False)
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(proposed)}],
                    }
                ]
            },
        )

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        report = await ConnectorPlanningAgent(http, settings).plan(
            vienna,
            {"url": recipe().source_url, **table.metadata()},
            validate_data=lambda proposal: trial_mapping(table, proposal),
        )
    assert len(calls) == 2 and report["attempts"] == 2
    assert report["data_validation"]["status"] == "data_checked" and not report["activated"]


async def test_probe_cleans_rows_even_when_model_fails(settings, vienna, monkeypatch):
    seen = []

    def capture(*args):
        table = read_table(*args)
        seen.append(table)
        return table

    async def fail_model(*args, **kwargs):
        raise ProviderError("ai_rate_limit", "Synthetic limit")

    monkeypatch.setattr("src.ingestion.probe.read_table", capture)
    monkeypatch.setattr(ConnectorPlanningAgent, "plan", fail_model)
    async with SafeHTTP(
        settings,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"id\nSECRET_AREA")),
        dns_check=allow_dns,
    ) as http:
        with pytest.raises(ProviderError):
            await probe_table(
                vienna, recipe().source_url, ReaderSpec(format="csv"), settings, http, use_ai=True
            )
    assert seen and not seen[0].rows and not seen[0].geometries
