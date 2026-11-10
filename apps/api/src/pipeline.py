import asyncio
import json

from .config import Settings
from .connectors.census import gather_cancel
from .connectors.registry import select_connector
from .discovery.agents import discover_sources
from .discovery.census_builder import build_census_connector
from .http import ProviderError, SafeHTTP
from .models import AnalysisRequest, Event, Place
from .statistics.indices import InvalidDistribution, compute_metrics, validate_counts


def event(name, **data):
    return Event(event=name, data=data)


async def analysis_events(
    place: Place, request: AnalysisRequest, settings: Settings, http: SafeHTTP
):
    dataset = raw = polygons = counties = geojson = None
    sources = []
    try:
        yield event(
            "started", place=place.model_dump(mode="json"), message="Identification des sources"
        )
        yield event(
            "geography_ready",
            place=place.model_dump(mode="json"),
            boundary=None,
            extent_description="Point du répertoire mondial ; limite municipale non vérifiée",
        )
        async with asyncio.timeout(settings.analysis_timeout_seconds):
            connector, reason = select_connector(place, http, settings)
            year = request.requested_year or settings.acs_year
            builder_report = None
            if connector is None and place.country_code == "US":
                yield event(
                    "discovery_progress",
                    agent="geography",
                    status="running",
                    message="Recherche d’un connecteur ACS et vérification des limites de la commune",
                )
                try:
                    connector, builder_report = await build_census_connector(
                        place, year, http, settings
                    )
                    reason = connector.extent_description
                except ProviderError as exc:
                    builder_report = {
                        "status": "blocked",
                        "template": "census_acs_county_equivalent",
                        "activated": False,
                        "message": exc.message,
                        "code": exc.code,
                    }
                yield event(
                    "discovery_progress",
                    agent="connector",
                    status=builder_report["status"],
                    message=builder_report["message"],
                    report=builder_report,
                )
            if connector is None:
                yield event(
                    "discovery_progress",
                    agent="sources",
                    status="running",
                    message="Recherche de sources Web et inspection des catalogues officiels",
                )
                discovery = await discover_sources(place, http, settings)
                web = discovery.get("web_discovery", {})
                for step in web.get("trace", []):
                    yield event(
                        "discovery_progress",
                        agent="web_research",
                        status=step["status"],
                        message=step["message"]
                        + (" : " + step["query"] if step.get("query") else ""),
                    )
                yield event(
                    "discovery_progress",
                    agent="web_search",
                    status=web.get("status", "not_configured"),
                    message=web.get("reason", "Recherche Web non configurée"),
                )
                if builder_report:
                    discovery.setdefault("connector_proposals", []).insert(0, builder_report)
                for proposal in discovery.get("connector_proposals", []):
                    yield event(
                        "discovery_progress",
                        agent="connector",
                        status=proposal["status"],
                        message=proposal.get(
                            "message", "Proposition examinée par les contrôles de données"
                        ),
                        report=proposal,
                    )
                yield event("insufficient_data", **discovery)
                yield event("complete", status="insufficient_data")
                return
            sources, counties = await gather_cancel(
                connector.discover(place, year), connector.get_extent(year)
            )
            for source in sources:
                yield event("source_found", source=source.model_dump(mode="json"))
            outline = await asyncio.to_thread(connector.outline, counties)
            yield event(
                "geography_ready",
                place=place.model_dump(mode="json"),
                boundary=outline,
                extent_description=reason,
                source=counties["provenance"],
            )
            yield event(
                "downloading", message="Téléchargement ACS et TIGERweb en parallèle", year=year
            )
            raw, polygons = await gather_cancel(
                connector.fetch(sources[0], place), connector.get_boundaries(year)
            )
            yield event(
                "validating",
                message="Vérification des revenus, millésimes, géométries et jointures exactes",
            )
            dataset = connector.normalize(raw, sources[0], place)
            raw.clear()
            raw = None
            counts = validate_counts([a.counts for a in dataset.areas])
            geojson, coverage, warnings = await asyncio.to_thread(
                connector.validate_geography, dataset, polygons, counties
            )
            yield event(
                "map_ready",
                geojson=geojson,
                coverage=coverage,
                warnings=warnings,
                income=dataset.income.model_dump(mode="json"),
                year=year,
                composition=counts.sum(axis=0).astype(int).tolist(),
                sources=[s.model_dump(mode="json") for s in sources] + [polygons["provenance"]],
                export_allowed=all(source.permissions == "public_domain" for source in sources),
                status="measured",
            )
            preferences = request.indices
            basic = [
                k
                for k in ("dissimilarity", "isolation", "exposure", "theil_h")
                if preferences is None or k in preferences
            ]
            for metric in compute_metrics(counts, basic):
                yield event("metric_computed", metric=metric.model_dump(mode="json"))
            if preferences is None or "rank_order_h" in preferences:
                rank_metrics = await asyncio.to_thread(compute_metrics, counts, ["rank_order_h"])
                for metric in rank_metrics:
                    yield event("metric_computed", metric=metric.model_dump(mode="json"))
            yield event(
                "complete",
                status="measured",
                message="Analyse terminée ; données conservées uniquement dans cette session du navigateur",
            )
    except ProviderError as exc:
        outcome = (
            "failed"
            if exc.code in {"provider_timeout", "provider_busy", "provider_dns"}
            else "insufficient_data"
        )
        yield event(
            outcome,
            status=outcome,
            code=exc.code,
            reason=exc.message,
            sources_attempted=[s.model_dump(mode="json") for s in sources],
            missing=["Données officielles complètes et validées pour ce millésime"],
        )
        yield event("complete", status=outcome)
    except InvalidDistribution as exc:
        yield event(
            "insufficient_data",
            status="insufficient_data",
            code="invalid_distribution",
            reason=str(exc),
        )
        yield event("complete", status="insufficient_data")
    except TimeoutError:
        yield event(
            "failed",
            status="failed",
            code="analysis_timeout",
            reason="Le délai maximal de l’analyse est dépassé. Les fournisseurs officiels peuvent être lents ; réessayez.",
        )
        yield event("complete", status="failed")
    finally:
        # No dataset escapes this generator except through the current response.
        if isinstance(raw, list):
            raw.clear()
        if dataset is not None:
            dataset.areas.clear()
        for data in (polygons, counties, geojson):
            if isinstance(data, dict):
                data.clear()


def encode_event(item: Event) -> bytes:
    return (
        json.dumps(
            item.model_dump(mode="json"), ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    ).encode()
