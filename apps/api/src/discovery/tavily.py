"""Bounded Tavily Search access; credentials go only to its fixed API origin."""

import asyncio
import json

import httpx

from ..http import ProviderError, public_dns


def free_allowance(payload, reserve=10):
    """Require free plan and spare included credits; never rely on PAYGO.

    Researcher returns null for its optional PAYGO limit. Null does not prove
    billing settings; the operator must keep PAYGO disabled on the account.
    """
    try:
        account = payload["account"]
        plan = account["current_plan"].strip().lower()
        numbers = [account[k] for k in ("plan_limit", "plan_usage", "paygo_usage")]
        if any(type(n) is not int or n < 0 for n in numbers):
            raise ValueError
        limit, used, paygo_used = numbers
        paygo_limit = account["paygo_limit"]
        if (
            plan not in {"researcher", "free"}
            or not 0 < limit <= 1000
            or paygo_limit not in (None, 0)
            or paygo_used
        ):
            raise ProviderError(
                "search_paid_plan",
                "La recherche exige l’offre gratuite Tavily et le paiement à l’usage désactivé.",
            )
        if used + reserve >= limit:
            raise ProviderError(
                "search_quota",
                "Le quota gratuit Tavily est épuisé ; aucune recherche facturable n’est lancée.",
            )
        key = payload["key"]
        if key.get("limit") is not None:
            if type(key["limit"]) is not int or type(key.get("usage")) is not int:
                raise ValueError
            if key["usage"] >= key["limit"]:
                raise ProviderError("search_quota", "Le quota de cette clé Tavily est atteint.")
        return limit - used
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ProviderError(
            "search_usage_schema",
            "Impossible de vérifier le quota gratuit Tavily ; recherche suspendue.",
        ) from exc


async def tavily_query(query, settings, *, budget=None, transport=None, dns_check=public_dns):
    secret = settings.tavily_api_key.get_secret_value()
    if not secret:
        raise ProviderError(
            "search_not_configured",
            "Ajouter la clé gratuite Tavily dans TAVILY_API_KEY pour activer la recherche Web.",
        )
    await dns_check("api.tavily.com")
    try:
        async with (
            asyncio.timeout(25),
            httpx.AsyncClient(
                timeout=15,
                trust_env=False,
                follow_redirects=False,
                transport=transport,
            ) as client,
        ):

            async def request(path, body=None):
                async with client.stream(
                    "POST" if body is not None else "GET",
                    "https://api.tavily.com" + path,
                    headers={"Authorization": "Bearer " + secret, "Accept-Encoding": "identity"},
                    json=body,
                ) as response:
                    if response.status_code != 200:
                        code = (
                            "search_quota"
                            if response.status_code in (429, 432, 433)
                            else "search_provider"
                        )
                        raise ProviderError(
                            code,
                            f"Tavily a répondu HTTP {response.status_code} ; aucune relance ou solution payante automatique.",
                        )
                    raw = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=16384):
                        if budget is not None:
                            budget.received += len(chunk)
                        if len(raw) + len(chunk) > 1_000_000 or (
                            budget is not None
                            and budget.received > settings.max_request_download_bytes
                        ):
                            raise ProviderError(
                                "search_limit", "Réponse de recherche au-delà du budget."
                            )
                        raw.extend(chunk)
                    return json.loads(raw)

            if settings.tavily_free_only:
                free_allowance(
                    await request("/usage"),
                    reserve=max(
                        10, settings.max_concurrent_analyses * settings.discovery_max_searches
                    ),
                )
            result = await request(
                "/search",
                {
                    "query": query,
                    "search_depth": "basic",
                    "auto_parameters": False,
                    "topic": "general",
                    "max_results": 5,
                    "include_answer": False,
                    "include_raw_content": False,
                    "include_images": False,
                },
            )
            if not isinstance(result, dict) or not isinstance(result.get("results"), list):
                raise ValueError
            return result["results"][:5]
    except (httpx.HTTPError, TimeoutError, ValueError, TypeError) as exc:
        raise ProviderError(
            "search_response", "Tavily est indisponible ou sa réponse est incompatible."
        ) from exc
