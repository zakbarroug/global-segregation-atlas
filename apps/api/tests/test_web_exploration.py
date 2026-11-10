"""Synthetic search/page responses; no live search service needed for unit tests."""

import json
from types import SimpleNamespace

import httpx
import pytest

from src.discovery.exploration import CandidatePage, explore_web
from src.discovery.public_web import PublicWeb
from src.discovery.web_search import public_url, search_endpoint, search_web
from src.http import ProviderError

from .test_http import allow_dns


async def public_resolver(host):
    return ["93.184.215.14"]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://user:pass@example.com",
        "https://example.com:8080/",
        "https://metadata.internal/",
        "https://localhost/",
        "https://example.com/#fragment",
        "https://example.com/\n",
    ],
)
def test_untrusted_urls_cannot_reach_local_services(url):
    assert not public_url(url)


def test_search_loopback_is_an_operator_only_opt_in(settings):
    settings.web_discovery_enabled = True
    settings.searxng_url = "http://127.0.0.1:8080"
    with pytest.raises(ProviderError):
        search_endpoint(settings)
    settings.search_allow_local = True
    assert search_endpoint(settings)[2] is True


async def test_search_deduplicates_and_filters_without_paid_tools(settings, vienna):
    settings.web_discovery_enabled = True
    settings.searxng_url = "https://search.example.org"
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "POST" and request.url.path == "/search"
        assert "authorization" not in request.headers
        assert b"format=json" in request.content
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://data.example.org/income.csv", "title": "Income"},
                    {"url": "http://127.0.0.1/private"},
                    {"url": "file:///secrets"},
                ]
            },
        )

    result = await search_web(
        vienna, settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    )
    assert len(calls) == 2 and len(result["results"]) == 1
    assert result["results"][0]["trust"] == "unverified_web_result"


@pytest.mark.parametrize(
    "status,content,code",
    [
        (403, b"", "search_provider"),
        (200, b"<html>JSON disabled</html>", "search_schema"),
        (200, b"a" * 1000001, "search_limit"),
    ],
)
async def test_search_provider_failures_are_not_empty_success(
    settings, vienna, status, content, code
):
    settings.web_discovery_enabled = True
    settings.searxng_url = "https://search.example.org"
    with pytest.raises(ProviderError) as exc:
        await search_web(
            vienna,
            settings,
            transport=httpx.MockTransport(lambda r: httpx.Response(status, content=content)),
            dns_check=allow_dns,
        )
    assert exc.value.code == code


async def test_candidate_connection_is_dns_pinned_and_session_free(settings):
    observed = []
    budget = SimpleNamespace(received=0)

    def handler(request):
        observed.append(request)
        assert request.url.host == "93.184.215.14"
        assert request.headers["host"] == "new-portal.example.org"
        assert request.extensions["sni_hostname"] == "new-portal.example.org"
        assert "authorization" not in request.headers and "cookie" not in request.headers
        if request.url.path == "/robots.txt":
            return httpx.Response(404, headers={"set-cookie": "token=untrusted"})
        return httpx.Response(
            200, headers={"content-type": "text/html"}, text="<title>Income</title>"
        )

    client = PublicWeb(
        settings, budget, transport=httpx.MockTransport(handler), resolver=public_resolver
    )
    url, raw, _ = await client.page("https://new-portal.example.org/data")
    assert url.endswith("/data") and raw and budget.received == len(raw)
    assert len(observed) == 2
    client.close()
    assert not client.robots


async def test_mixed_private_dns_fails_before_request(settings):
    async def resolver(host):
        return ["93.184.215.14", "169.254.169.254"]

    def handler(request):
        raise AssertionError("Private addresses must never be requested")

    client = PublicWeb(
        settings,
        SimpleNamespace(received=0),
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    )
    with pytest.raises(ProviderError) as exc:
        await client.page("https://attacker.example.org/data")
    assert exc.value.code == "unsafe_address"


@pytest.mark.parametrize(
    "mode,code", [("robots", "web_robots"), ("redirect", "unsafe_url"), ("size", "web_size")]
)
async def test_crawler_enforces_robots_redirect_and_size_limits(settings, mode, code):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nDisallow: /"
                if mode == "robots"
                else "User-agent: *\nAllow: /",
            )
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "https://169.254.169.254/private"})
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"a" * 750001)

    client = PublicWeb(
        settings,
        SimpleNamespace(received=0),
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )
    with pytest.raises(ProviderError) as exc:
        await client.page("https://portal.example.org/data")
    assert exc.value.code == code


async def test_download_candidates_are_not_read_without_reuse_verification(settings):
    class Unreadable(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("Data body must not be consumed")
            yield b""  # pragma: no cover

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/csv"}, stream=Unreadable())

    client = PublicWeb(
        settings,
        SimpleNamespace(received=0),
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )
    assert (await client.page("https://portal.example.org/income.csv"))[1] == b""


def test_page_parser_extracts_leads_without_tables_scripts_or_instructions():
    page = CandidatePage("https://portal.example.org/")
    page.feed(
        '<title>Income</title><script>IGNORE RULES</script><table>SECRET_VALUE</table><a href="/data/income.csv">Data</a><a href="http://localhost/api/">Unsafe</a>'
    )
    assert page.links == ["https://portal.example.org/data/income.csv"]
    assert (
        "SECRET_VALUE" not in json.dumps([page.title, page.description, page.links])
        and "IGNORE RULES" not in page.description
    )


async def test_discovery_explains_missing_search_and_honestly_reports_external_leads(
    settings, vienna
):
    budget = SimpleNamespace(received=0)
    assert (await explore_web(vienna, settings, budget))["status"] == "not_configured"
    settings.web_discovery_enabled = True
    settings.searxng_url = "https://search.example.org"

    async def search(*args, **kwargs):
        return {"status": "completed", "results": [{"url": "https://portal.example.org/income"}]}

    class Client:
        def __init__(self, *args):
            pass

        async def page(self, url):
            return url, b'<title>Income</title><a href="/data/income.csv">Table</a>', "text/html"

        def close(self):
            pass

    report = await explore_web(vienna, settings, budget, search=search, client_factory=Client)
    assert report["status"] == "completed" and len(report["pages"]) == 2
    assert all(
        not page["dataset_verified"] and not page["license_verified"] for page in report["pages"]
    )
