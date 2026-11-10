import httpx
import pytest

from src.http import ProviderError, SafeHTTP, public_dns, validate_url


async def allow_dns(_):
    return None


@pytest.mark.parametrize(
    "url",
    [
        "http://api.census.gov/data",
        "https://localhost/",
        "https://127.0.0.1/",
        "https://169.254.169.254/latest/meta-data/",
        "https://api.census.gov.evil.test/",
        "https://evil.test@api.census.gov/",
        "https://api.census.gov:8080/",
        "file:///etc/passwd",
    ],
)
def test_ssrf_urls_rejected(url):
    with pytest.raises(ProviderError, match="reviewed"):
        validate_url(url)


async def test_redirect_never_followed(settings):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secrets"})

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        with pytest.raises(ProviderError) as error:
            await http.json("https://api.census.gov/data")
    assert error.value.code == "provider_redirect" and len(calls) == 1


async def test_response_size_limit(settings):
    async with SafeHTTP(
        settings,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 2000)),
        dns_check=allow_dns,
    ) as http:
        with pytest.raises(ProviderError) as error:
            await http.fetch("https://api.census.gov/data", max_bytes=100)
    assert error.value.code == "download_limit"


async def test_invalid_json(settings):
    async with SafeHTTP(
        settings,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text="<html>Invalid Key</html>")
        ),
        dns_check=allow_dns,
    ) as http:
        with pytest.raises(ProviderError) as error:
            await http.json("https://api.census.gov/data")
    assert error.value.code == "invalid_json"


async def test_timeout_bounded_and_redacted(settings, monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("secret-in-upstream-url", request=request)

    async def no_sleep(_):
        pass

    monkeypatch.setattr("src.http.asyncio.sleep", no_sleep)
    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        with pytest.raises(ProviderError) as error:
            await http.json("https://api.census.gov/data")
    assert calls == 3 and "secret" not in error.value.message


async def test_retry_after_not_ignored(settings):
    async with SafeHTTP(
        settings,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(429, headers={"retry-after": "120"})
        ),
        dns_check=allow_dns,
    ) as http:
        with pytest.raises(ProviderError) as error:
            await http.json("https://api.census.gov/data")
    assert error.value.code == "provider_busy"


async def test_private_dns_rejected(monkeypatch):
    import asyncio

    async def fake(*args, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake)
    with pytest.raises(ProviderError) as error:
        await public_dns("api.census.gov")
    assert error.value.code == "unsafe_address"
