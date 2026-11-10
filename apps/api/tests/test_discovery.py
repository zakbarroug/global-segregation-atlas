import json

import httpx
import pytest

from src.discovery.agents import (
    OpenAISourceAgent,
    Proposal,
    SourceVerificationAgent,
    discover_sources,
)
from src.http import ProviderError, SafeHTTP

from .provider_fixtures import official_handler
from .test_http import allow_dns


async def test_ai_candidates_are_bounded_and_only_official_hosts(settings, vienna):
    def handler(request):
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["max_tool_calls"] == 2
        assert "income_counts" not in request.content.decode()
        assert body["tools"][0]["filters"]["allowed_domains"]
        candidate = {
            "url": "https://www.statistik.at/test-source",
            "title": "Synthetic candidate",
            "publisher": "Statistics Austria",
            "reason": "Needs review",
            "license_url": None,
        }
        malicious = {**candidate, "url": "https://evil.test/exfiltrate"}
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"candidates": [candidate, malicious]}),
                            }
                        ],
                    }
                ]
            },
        )

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(handler), dns_check=allow_dns
    ) as http:
        candidates = await OpenAISourceAgent(http, settings).propose(vienna)
    assert len(candidates) == 1 and candidates[0].url.host == "www.statistik.at"


async def test_reachable_metadata_never_grants_processing_permission(settings):
    async with SafeHTTP(
        settings, transport=httpx.MockTransport(official_handler), dns_check=allow_dns
    ) as http:
        report = await SourceVerificationAgent(http).verify(
            Proposal(
                url="https://www.hcp.ma/",
                publisher="HCP",
                title="Metadata",
                reason="Not reviewed",
                license_url=None,
            )
        )
    assert report["status"] == "metadata_reachable"
    assert (
        not report["dataset_verified"]
        and not report["license_verified"]
        and not report["adapter_available"]
    )


async def test_unreviewed_proposal_never_fetches(settings):
    def reject_request(request):
        raise AssertionError("No HTTP should be sent")

    async with SafeHTTP(
        settings, transport=httpx.MockTransport(reject_request), dns_check=allow_dns
    ) as http:
        report = await SourceVerificationAgent(http).verify(
            Proposal(
                url="https://localhost/private",
                publisher="Untrusted",
                title="Test",
                reason="Untrusted",
                license_url=None,
            )
        )
    assert report["code"] == "unsafe_url"


async def test_discovery_without_key_is_honest(settings, vienna):
    settings.enable_ai_discovery = True
    async with SafeHTTP(
        settings, transport=httpx.MockTransport(official_handler), dns_check=allow_dns
    ) as http:
        result = await discover_sources(vienna, http, settings)
    assert result["ai_discovery"] == "missing_key" and result["status"] == "insufficient_data"


async def test_model_invalid_schema_rejected(settings, vienna):
    async with SafeHTTP(
        settings,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"output": []})),
        dns_check=allow_dns,
    ) as http:
        with pytest.raises(ProviderError) as error:
            await OpenAISourceAgent(http, settings).propose(vienna)
    assert error.value.code == "discovery_schema"
