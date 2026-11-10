import asyncio
import json

import httpx
import pytest

from src.connectors.census import gather_cancel
from src.http import ProviderError
from src.main import create_app
from src.pipeline import event

from .test_api import mock_http


async def test_failed_provider_cancels_sibling_download():
    sibling_cancelled = asyncio.Event()
    sibling_started = asyncio.Event()

    async def sibling():
        sibling_started.set()
        try:
            await asyncio.sleep(100)
        finally:
            sibling_cancelled.set()

    async def failure():
        await sibling_started.wait()
        raise ProviderError("test", "Synthetic failure")

    with pytest.raises(ProviderError):
        await gather_cancel(sibling(), failure())
    assert sibling_cancelled.is_set()


async def test_cancelled_stream_releases_capacity(settings, nyc, monkeypatch):
    settings.max_concurrent_analyses = 1
    started = asyncio.Event()
    release = asyncio.Event()
    cleaned = asyncio.Event()

    async def slow_events(*args):
        try:
            started.set()
            yield event("started", message="Synthetic test")
            await release.wait()
            yield event("complete", status="insufficient_data")
        finally:
            cleaned.set()

    monkeypatch.setattr("src.main.analysis_events", slow_events)
    app = create_app(settings, mock_http)
    payload = {"city_id": app.state.tokens.encode(nyc)}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        abandoned = asyncio.create_task(client.post("/analysis", json=payload))
        await asyncio.wait_for(started.wait(), 3)
        assert (await client.post("/analysis", json=payload)).status_code == 429
        abandoned.cancel()
        with pytest.raises(asyncio.CancelledError):
            await abandoned
        assert cleaned.is_set()
        release.set()
        response = await client.post("/analysis", json=payload)
        assert response.status_code == 200
        assert json.loads(response.text.splitlines()[-1])["event"] == "complete"


def test_response_budget_ends_with_failure(settings, nyc):
    from fastapi.testclient import TestClient

    settings.max_response_bytes = 1000
    app = create_app(settings, mock_http)
    with TestClient(app) as client:
        response = client.post("/analysis", json={"city_id": app.state.tokens.encode(nyc)})
        events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["data"]["status"] == "failed"
    assert any(item["data"].get("code") == "response_limit" for item in events)


async def test_overall_deadline_cancels_source_discovery(settings, nyc, monkeypatch):
    from src.models import AnalysisRequest
    from src.pipeline import analysis_events

    settings.analysis_timeout_seconds = 0.01

    async def slow(*args):
        await asyncio.sleep(100)

    monkeypatch.setattr("src.connectors.census.CensusNYCConnector.discover", slow)
    async with mock_http(settings) as http:
        events = [
            item
            async for item in analysis_events(
                nyc, AnalysisRequest(city_id="synthetic-token"), settings, http
            )
        ]
    assert any(item.data.get("code") == "analysis_timeout" for item in events)
    assert events[-1].data["status"] == "failed"
