"""SearXNG adapter. Result URLs are leads, never trusted data-source permissions."""

import asyncio
import ipaddress
import json
from urllib.parse import urlsplit

import httpx

from ..http import ProviderError, public_dns
from .tavily import tavily_query


def search_available(settings):
    return settings.web_discovery_enabled and bool(
        settings.tavily_api_key.get_secret_value()
        if settings.web_search_provider == "tavily"
        else settings.searxng_url
    )


TERMS = {
    "FR": ("fr", "revenus ménages tranches quartier données ouvertes"),
    "MA": ("fr", "revenus ménages tranches quartier recensement"),
    "AT": ("de", "Haushaltseinkommen Einkommensklassen Stadtteile Statistik"),
    "DE": ("de", "Haushaltseinkommen Einkommensklassen Stadtteile Statistik"),
    "BR": ("pt", "renda domiciliar faixas setores censitários dados"),
    "ES": ("es", "ingresos hogares tramos secciones censales datos"),
}


def public_url(url):
    """Syntactic screening; every actual download additionally checks and pins DNS."""
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or parts.fragment
            or len(url) > 2000
            or any(ord(c) < 32 for c in url)
        ):
            return False
        try:
            return ipaddress.ip_address(parts.hostname).is_global
        except ValueError:
            return "." in parts.hostname and not parts.hostname.endswith(
                (".local", ".internal", ".localhost")
            )
    except ValueError:
        return False


def search_endpoint(settings):
    if not settings.web_discovery_enabled or not settings.searxng_url:
        raise ProviderError(
            "search_not_configured",
            "La recherche Web n’est pas activée : aucune instance SearXNG n’est configurée.",
        )
    try:
        parts = urlsplit(settings.searxng_url)
        if not parts.hostname or parts.query or parts.fragment or parts.username or parts.password:
            raise ValueError
        try:
            local = ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            local = False
        if local:
            if not settings.search_allow_local or parts.scheme not in {"http", "https"}:
                raise ValueError
        elif parts.scheme != "https" or parts.port not in (None, 443):
            raise ValueError
    except ValueError as exc:
        raise ProviderError(
            "search_configuration",
            "L’instance de recherche doit être en HTTPS public, ou en loopback explicitement autorisé.",
        ) from exc
    return settings.searxng_url.rstrip("/") + "/search", parts.hostname, local


def queries(place):
    language, terms = TERMS.get(
        place.country_code, ("en", "household income brackets census tract open data")
    )
    # Both the selected city and country disambiguate; never inject search syntax from model output.
    label = " ".join(place.label.replace('"', " ").split())[:100]
    country = " ".join(place.country.replace('"', " ").split())[:80]
    return [
        (f'"{label}" "{country}" {terms}', language),
        (f'"{label}" "{country}" census small area household income distribution boundaries', "en"),
    ]


async def search_web(
    place, settings, *, transport=None, dns_check=public_dns, budget=None, query=None
):
    if not settings.web_discovery_enabled:
        raise ProviderError("search_not_configured", "Recherche Web désactivée sur ce serveur.")
    selected_queries = [(query, "all")] if query is not None else queries(place)
    if any(
        not isinstance(q, str) or not 2 <= len(q) <= 400 or any(ord(c) < 32 for c in q)
        for q, _ in selected_queries
    ):
        raise ProviderError("search_query", "Requête de recherche invalide ou trop longue.")
    if settings.web_search_provider == "tavily":
        found, seen = [], set()
        for q, _ in selected_queries:
            entries = await tavily_query(
                q, settings, budget=budget, transport=transport, dns_check=dns_check
            )
            for item in entries:
                target = item.get("url", "") if isinstance(item, dict) else ""
                if isinstance(target, str) and public_url(target) and target not in seen:
                    seen.add(target)
                    found.append(
                        {
                            "url": target,
                            "title": str(item.get("title", ""))[:300],
                            "description": str(item.get("content", ""))[:800],
                            "publisher": urlsplit(target).hostname,
                            "trust": "unverified_web_result",
                        }
                    )
        return {
            "status": "completed",
            "queries": [q for q, _ in selected_queries],
            "results": found[:10],
        }
    url, host, local = search_endpoint(settings)
    if not local:
        await dns_check(host)
    results, seen, attempted = [], set(), []
    async with (
        asyncio.timeout(25),
        httpx.AsyncClient(
            timeout=12, follow_redirects=False, trust_env=False, transport=transport
        ) as client,
    ):
        for query, language in selected_queries:
            attempted.append(query)
            async with client.stream(
                "POST",
                url,
                data={
                    "q": query,
                    "language": language,
                    "format": "json",
                    "categories": "general",
                    "pageno": "1",
                    "safesearch": "1",
                },
            ) as response:
                if response.status_code != 200:
                    raise ProviderError(
                        "search_provider",
                        f"Le moteur de recherche a répondu HTTP {response.status_code} ; aucun autre service payant n’est appelé.",
                    )
                raw = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=16384):
                    if budget is not None:
                        budget.received += len(chunk)
                        if budget.received > settings.max_request_download_bytes:
                            raise ProviderError(
                                "search_limit", "Budget de téléchargement de la requête atteint."
                            )
                    if len(raw) + len(chunk) > 1_000_000:
                        raise ProviderError(
                            "search_limit", "Réponse du moteur de recherche trop volumineuse."
                        )
                    raw.extend(chunk)
            try:
                payload = json.loads(raw)
                entries = payload["results"]
                if not isinstance(entries, list):
                    raise ValueError
            except (ValueError, KeyError, TypeError) as exc:
                raise ProviderError(
                    "search_schema", "Le moteur doit autoriser les résultats JSON."
                ) from exc
            for item in entries[:20]:
                target = item.get("url", "") if isinstance(item, dict) else ""
                if not isinstance(target, str) or not public_url(target) or target in seen:
                    continue
                seen.add(target)
                results.append(
                    {
                        "url": target,
                        "title": str(item.get("title", ""))[:300],
                        "description": str(item.get("content", ""))[:800],
                        "publisher": urlsplit(target).hostname,
                        "trust": "unverified_web_result",
                    }
                )
                if len(results) >= 10:
                    break
    return {"status": "completed", "queries": attempted, "results": results[:10]}
