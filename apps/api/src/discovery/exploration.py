"""Find external leads without granting them data-processing or export permission."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from ..http import ProviderError
from .inspection import short
from .public_web import PublicWeb
from .research_agent import ResearchAgent
from .web_search import public_url, search_available, search_web


class CandidatePage(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.in_title = base, False
        self.title, self.description, self.links = "", "", []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and attrs.get("name", "").lower() == "description":
            self.description = short(attrs.get("content"))
        if tag == "a" and len(self.links) < 20:
            url = urljoin(self.base, attrs.get("href") or "")
            # Follow only dataset/catalog/download links, never forms or arbitrary site navigation.
            if (
                public_url(url)
                and re.search(
                    r"\.(csv|xlsx|json|geojson)(?:\?|$)|/(?:datasets?|data|api|download|resources?|MapServer|FeatureServer)(?:/|\?)|income|einkommen|revenu|licen[cs]|census|statistik|haushalt",
                    url,
                    re.I,
                )
                and url not in self.links
            ):
                self.links.append(url)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title = short(self.title + data, 300)


async def explore_web(
    place, settings, budget, *, search=search_web, client_factory=PublicWeb, decide=None
):
    if not search_available(settings):
        return {
            "status": "not_configured",
            "results": [],
            "pages": [],
            "trace": [],
            "reason": "Recherche Web inactive : configurer Tavily ou une instance SearXNG JSON.",
        }
    client = client_factory(settings, budget)

    async def search_tool(query):
        try:
            return await search(place, settings, budget=budget, query=query)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError(
                "search_response", "La recherche a renvoyé un résultat incompatible."
            ) from exc

    async def visit_tool(url):
        record = {
            "url": url,
            "publisher": urlsplit(url).hostname,
            "trust": "unverified_web_result",
            "dataset_verified": False,
            "license_verified": False,
            "adapter_available": False,
        }
        try:
            final, raw, content_type = await client.page(url)
            record.update(url=final, content_type=content_type)
            if raw:
                parser = CandidatePage(final)
                parser.feed(raw.decode("utf-8", errors="replace"))
                record.update(
                    status="metadata_reachable",
                    title=parser.title,
                    description=parser.description,
                    resources=parser.links,
                    reason="Page accessible ; autorité, données et licence restent à vérifier.",
                )
            else:
                record.update(
                    status="resource_identified",
                    reason="Ressource repérée ; la lecture des données attend la vérification de la source et des droits.",
                )
        except ProviderError as exc:
            record.update(status="not_verified", code=exc.code, reason=exc.message)
        return record

    try:
        return await ResearchAgent(
            place, settings, budget, search=search_tool, visit=visit_tool, decide=decide
        ).run()
    finally:
        client.close()
