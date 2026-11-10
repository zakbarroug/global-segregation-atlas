"""Only explicitly vetted HTTPS hosts, no redirects, request-scoped byte budgets."""

import asyncio
import ipaddress
import json
import socket
from urllib.parse import urlsplit

import httpx

from .config import Settings

VETTED_HOSTS = frozenset(
    {
        "api.census.gov",
        "tigerweb.geo.census.gov",
        "secure.geonames.org",
        "photon.komoot.io",
        "api.openai.com",
        "www.statistik.at",
        "data.statistik.gv.at",
        "www.wien.gv.at",
        "www.data.gv.at",
        "www.hcp.ma",
        "data.gov.ma",
        "www.census.gov",
        "www.ons.gov.uk",
        "api.ons.gov.uk",
        "www.insee.fr",
        "api.insee.fr",
        "www.statcan.gc.ca",
        "www150.statcan.gc.ca",
        "www.abs.gov.au",
        "www.ibge.gov.br",
        "servicodados.ibge.gov.br",
        "ec.europa.eu",
        "ckan.publishing.service.gov.uk",
        "data.sfgov.org",
    }
)


class ProviderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in VETTED_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port not in (443, None)
            or parsed.fragment
        ):
            raise ValueError
    except ValueError as exc:
        raise ProviderError(
            "unsafe_url", "Only reviewed public HTTPS provider URLs are allowed"
        ) from exc
    return parsed.hostname


async def public_dns(host: str):
    try:
        records = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ProviderError("provider_dns", "The provider hostname could not be resolved") from exc
    if not records or any(not ipaddress.ip_address(r[4][0]).is_global for r in records):
        raise ProviderError("unsafe_address", "Provider resolved to a non-public network")


class SafeHTTP:
    def __init__(self, settings: Settings, *, transport=None, dns_check=public_dns):
        self.settings = settings
        self.received = 0
        self.semaphore = asyncio.Semaphore(4)
        self.dns_check = dns_check
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout_seconds, connect=8),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
            headers={
                "User-Agent": "GlobalSegregationAtlas/0.1 (on-demand official-data research)",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.client.aclose()
        self.received = 0

    async def fetch(self, url, *, params=None, body=None, headers=None, max_bytes=None):
        host = validate_url(url)
        limit = min(max_bytes or self.settings.max_download_bytes, self.settings.max_download_bytes)
        for attempt in range(3):
            await self.dns_check(host)
            try:
                async with (
                    self.semaphore,
                    self.client.stream(
                        "POST" if body is not None else "GET",
                        url,
                        params=params,
                        json=body,
                        headers=headers,
                    ) as response,
                ):
                    if response.status_code in (429, 502, 503, 504):
                        if attempt == 2:
                            raise ProviderError(
                                "provider_busy", "Provider rate limit or temporary outage"
                            )
                        retry = response.headers.get("retry-after", "")
                        # Never retry earlier than a provider's requested delay.
                        if retry and (not retry.isdigit() or int(retry) > 5):
                            raise ProviderError(
                                "provider_busy",
                                "Provider requested a longer retry interval; try again later",
                            )
                        delay = max(float(retry or 0), 0.6 * (2**attempt))
                        await asyncio.sleep(delay)
                        continue
                    if 300 <= response.status_code < 400:
                        raise ProviderError(
                            "provider_redirect",
                            "Provider redirect refused; source metadata needs review",
                        )
                    if response.status_code != 200:
                        raise ProviderError(
                            "provider_http", f"Provider returned HTTP {response.status_code}"
                        )
                    if (
                        response.headers.get("content-length", "").isdigit()
                        and int(response.headers["content-length"]) > limit
                    ):
                        raise ProviderError(
                            "download_limit", "Provider response exceeds the download limit"
                        )
                    data = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        self.received += len(chunk)
                        if (
                            len(data) + len(chunk) > limit
                            or self.received > self.settings.max_request_download_bytes
                        ):
                            raise ProviderError(
                                "download_limit", "Request download budget exceeded"
                            )
                        data.extend(chunk)
                    return bytes(data), response.headers.get("content-type", "")
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise ProviderError(
                        "provider_timeout", "The official provider did not respond in time"
                    ) from exc
                await asyncio.sleep(0.6 * (2**attempt))
        raise ProviderError("provider_failed", "Provider request failed")

    async def json(self, url, **kwargs):
        raw, _ = await self.fetch(url, **kwargs)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderError(
                "invalid_json", "The provider returned invalid JSON (check API credentials)"
            ) from exc
        if isinstance(data, dict) and "error" in data:
            raise ProviderError(
                "provider_error",
                "The official API reported an error; check credentials, vintage and quotas",
            )
        return data
