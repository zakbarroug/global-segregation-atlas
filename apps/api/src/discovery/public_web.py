"""Credential-free, request-scoped Web inspection with DNS pinning and robots rules.

Unlike official-data connectors this client can inspect unknown public hosts.
It is not exposed as an HTTP proxy. Search results are leads, not official sources.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..http import ProviderError
from .web_search import public_url

USER_AGENT = "GlobalSegregationAtlas"


async def resolve_public(host):
    try:
        records = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(item[4][0] for item in records))
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ProviderError("unsafe_address", "Adresse réseau non publique : visite refusée.")
        return addresses
    except OSError as exc:
        raise ProviderError("web_dns", "Le domaine candidat ne peut pas être résolu.") from exc


class PublicWeb:
    def __init__(self, settings, budget, *, transport=None, resolver=resolve_public):
        self.settings, self.budget = settings, budget
        self.transport, self.resolver = transport, resolver
        self.requests, self.received, self.robots = 0, 0, {}

    async def _get(self, url, limit, *, html_only=False):
        if not public_url(url):
            raise ProviderError("unsafe_url", "Seules les URL HTTPS publiques sont inspectées.")
        if self.requests >= self.settings.discovery_max_pages * 4:
            raise ProviderError("web_budget", "Budget de visites Web atteint.")
        self.requests += 1
        original = httpx.URL(url)
        addresses = await self.resolver(original.host)
        # Defence in depth even when an alternative resolver is injected.
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ProviderError("unsafe_address", "Adresse réseau non publique : visite refusée.")
        pinned = original.copy_with(host=addresses[0])
        try:
            # A fresh client avoids all cookie/session forwarding between candidates.
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10, connect=5),
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "GET",
                    pinned,
                    headers={
                        "Host": original.host,
                        "User-Agent": USER_AGENT + "/0.1",
                        "Accept": "text/html,application/json;q=0.8,*/*;q=0.1",
                        "Accept-Encoding": "identity",
                    },
                    extensions={"sni_hostname": original.host},
                ) as response:
                    content_type = response.headers.get("content-type", "").lower()
                    location = response.headers.get("location")
                    if response.status_code != 200:
                        return response.status_code, b"", content_type, location
                    if html_only and not any(
                        t in content_type for t in ("text/html", "application/xhtml+xml")
                    ):
                        # Do not download observations before a reuse policy is verified.
                        return 200, b"", content_type, None
                    length = response.headers.get("content-length", "")
                    if length.isdigit() and int(length) > limit:
                        raise ProviderError(
                            "web_size", "Source au-delà du budget de téléchargement."
                        )
                    raw = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=16384):
                        self.received += len(chunk)
                        self.budget.received += len(chunk)
                        if (
                            len(raw) + len(chunk) > limit
                            or self.received > 8_000_000
                            or self.budget.received > self.settings.max_request_download_bytes
                        ):
                            raise ProviderError("web_size", "Budget de téléchargement Web atteint.")
                        raw.extend(chunk)
                    return 200, bytes(raw), content_type, None
        except httpx.HTTPError as exc:
            raise ProviderError("web_network", "La page candidate est indisponible.") from exc

    async def _allowed(self, url):
        parts = urlsplit(url)
        origin = f"https://{parts.netloc}"
        if origin not in self.robots:
            status, raw, _, _ = await self._get(origin + "/robots.txt", 150_000)
            if status in (404, 410):
                self.robots[origin] = None
            elif status == 200:
                rules = RobotFileParser()
                rules.parse(raw.decode("utf-8", errors="replace").splitlines())
                self.robots[origin] = rules
            else:
                raise ProviderError(
                    "web_robots",
                    "Règles de visite indisponibles ; aucune exploration supplémentaire.",
                )
        rules = self.robots[origin]
        if rules is not None:
            if not rules.can_fetch(USER_AGENT, url):
                raise ProviderError(
                    "web_robots", "La source refuse la visite automatisée de cette page."
                )
            delay = rules.crawl_delay(USER_AGENT)
            rate = rules.request_rate(USER_AGENT)
            if delay or rate:
                # No bypass of schedules; the bounded crawler skips these sites for now.
                raise ProviderError(
                    "web_robots", "La source impose un rythme de visites non pris en charge."
                )

    async def page(self, url):
        for _ in range(3):
            if not public_url(url):
                raise ProviderError("unsafe_url", "Redirection vers une URL interdite.")
            await self._allowed(url)
            status, raw, content_type, location = await self._get(url, 750_000, html_only=True)
            if status in (301, 302, 303, 307, 308) and location:
                url = urljoin(url, location)
                continue  # Recheck URL, robots and public DNS; never forward credentials.
            if status != 200:
                raise ProviderError("web_http", f"Page candidate indisponible (HTTP {status}).")
            return url, raw, content_type
        raise ProviderError("web_redirect", "Trop de redirections pour cette source.")

    def close(self):
        self.robots.clear()
