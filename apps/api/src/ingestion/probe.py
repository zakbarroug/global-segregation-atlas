"""Trial a reviewed file in RAM. No publication, arbitrary execution or stored data."""

import asyncio

from ..discovery.planner import ConnectorPlanningAgent
from .readers import read_table
from .validation import trial_mapping


async def probe_table(
    place, url, spec, settings, http, *, params=None, field_metadata=None, use_ai=False
):
    """Operator/internal use only, with vetted SafeHTTP and an already reviewed reuse policy.

    The caller supplies authoritative field labels when available. Neither model
    proposals nor search results are allowed to invoke this function directly.
    """
    table = raw = None
    try:
        raw, _ = await http.fetch(url, params=params, max_bytes=10_000_000)
        table = await asyncio.to_thread(read_table, raw, spec, settings)
        raw = None
        inspection = {"url": url, "status": "read", "resources": [], **table.metadata()}
        if field_metadata:
            for field in inspection["fields"]:
                authoritative = field_metadata.get(field["name"], {})
                field["label"] = str(authoritative.get("label", field["label"]))[:300]
        result = {
            "inspection": inspection,
            "activated": False,
            "message": "Fichier lu intégralement en mémoire ; validation scientifique et géographique encore requise.",
        }
        if use_ai:
            result["proposal"] = await ConnectorPlanningAgent(http, settings).plan(
                place,
                inspection,
                validate_data=lambda recipe: trial_mapping(table, recipe),
            )
        return result
    finally:
        if table is not None:
            table.close()
        raw = None
