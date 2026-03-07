"""Tests for data/sentiment_feed.py — Fear & Greed index (mocked)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from data.sentiment_feed import get_fear_greed
from data.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


MOCK_FNG_RESPONSE = {
    "name": "Fear and Greed Index",
    "data": [
        {
            "value": "23",
            "value_classification": "Extreme Fear",
            "timestamp": "1709510400",
        }
    ],
}


def _mock_httpx_client(json_data=None, raise_on_get=None):
    """Build a mock httpx.AsyncClient with sync json()/raise_for_status()."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data if json_data is not None else MOCK_FNG_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    if raise_on_get:
        mock_client.get = AsyncMock(side_effect=raise_on_get)
    else:
        mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.mark.asyncio
async def test_get_fear_greed_returns_correct_structure():
    """Verify response has value, classification, timestamp."""
    mock_client = _mock_httpx_client()

    with patch("data.sentiment_feed.httpx.AsyncClient", return_value=mock_client):
        result = await get_fear_greed()

    assert result["value"] == 23
    assert result["classification"] == "Extreme Fear"
    assert result["timestamp"] == "1709510400"


@pytest.mark.asyncio
async def test_get_fear_greed_value_is_int():
    """Verify value is cast to int."""
    data = {"data": [{"value": "72", "value_classification": "Greed", "timestamp": "1709510400"}]}
    mock_client = _mock_httpx_client(json_data=data)

    with patch("data.sentiment_feed.httpx.AsyncClient", return_value=mock_client):
        result = await get_fear_greed()

    assert isinstance(result["value"], int)
    assert result["value"] == 72


@pytest.mark.asyncio
async def test_get_fear_greed_uses_cache():
    """Second call should use cache."""
    mock_client = _mock_httpx_client()

    with patch("data.sentiment_feed.httpx.AsyncClient", return_value=mock_client):
        r1 = await get_fear_greed()
        r2 = await get_fear_greed()

    assert r1 == r2
    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_get_fear_greed_empty_data():
    """Empty data should return neutral defaults."""
    mock_client = _mock_httpx_client(json_data={"data": []})

    with patch("data.sentiment_feed.httpx.AsyncClient", return_value=mock_client):
        result = await get_fear_greed()

    assert result["value"] == 50
    assert result["classification"] == "Neutral"


@pytest.mark.asyncio
async def test_get_fear_greed_api_failure_returns_neutral():
    """API error after retries should return neutral defaults."""
    mock_client = _mock_httpx_client(raise_on_get=Exception("timeout"))

    with patch("data.sentiment_feed.httpx.AsyncClient", return_value=mock_client):
        with patch("data.sentiment_feed.RETRY_BASE_DELAY", 0.01):
            result = await get_fear_greed()

    assert result["value"] == 50
    assert result["classification"] == "Neutral"
