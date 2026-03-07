"""Tests for data/funding_feed.py — Binance Futures funding rate (mocked)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from data.funding_feed import get_funding
from data.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


MOCK_FUNDING_RESPONSE = [
    {
        "symbol": "BTCUSDT",
        "fundingTime": 1709510400000,
        "fundingRate": "0.00015",
        "markPrice": "62300.00",
    }
]


def _mock_httpx_client(json_data=None, raise_on_get=None):
    """Build a mock httpx.AsyncClient context manager with sync json()/raise_for_status()."""
    mock_resp = MagicMock()  # MagicMock so .json() and .raise_for_status() are sync
    mock_resp.json.return_value = json_data if json_data is not None else MOCK_FUNDING_RESPONSE
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
async def test_get_funding_returns_correct_structure():
    """Verify funding response has rate, timestamp, asset."""
    mock_client = _mock_httpx_client()

    with patch("data.funding_feed.httpx.AsyncClient", return_value=mock_client):
        result = await get_funding("BTC")

    assert result["asset"] == "BTC"
    assert result["rate"] == 0.00015
    assert result["timestamp"] == 1709510400000


@pytest.mark.asyncio
async def test_get_funding_parses_rate_as_float():
    """Verify rate is properly converted to float."""
    data = [{"symbol": "ETHUSDT", "fundingTime": 1709510400000, "fundingRate": "-0.00032"}]
    mock_client = _mock_httpx_client(json_data=data)

    with patch("data.funding_feed.httpx.AsyncClient", return_value=mock_client):
        result = await get_funding("ETH")

    assert isinstance(result["rate"], float)
    assert result["rate"] == pytest.approx(-0.00032)


@pytest.mark.asyncio
async def test_get_funding_uses_cache():
    """Second call should use cache."""
    mock_client = _mock_httpx_client()

    with patch("data.funding_feed.httpx.AsyncClient", return_value=mock_client):
        r1 = await get_funding("BTC")
        r2 = await get_funding("BTC")

    assert r1 == r2
    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_get_funding_empty_response():
    """Empty API response should return safe defaults."""
    mock_client = _mock_httpx_client(json_data=[])

    with patch("data.funding_feed.httpx.AsyncClient", return_value=mock_client):
        result = await get_funding("BTC")

    assert result["rate"] == 0.0
    assert result["asset"] == "BTC"


@pytest.mark.asyncio
async def test_get_funding_api_failure_returns_defaults():
    """API error after retries should return safe defaults."""
    mock_client = _mock_httpx_client(raise_on_get=Exception("connection refused"))

    with patch("data.funding_feed.httpx.AsyncClient", return_value=mock_client):
        with patch("data.funding_feed.RETRY_BASE_DELAY", 0.01):
            result = await get_funding("BTC")

    assert result["rate"] == 0.0
    assert result["timestamp"] == 0
    assert result["asset"] == "BTC"
