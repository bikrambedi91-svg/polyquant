"""Tests for data/price_feed.py — OHLCV via Binance direct + Coinbase fallback."""

import pytest
import pandas as pd
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from data.price_feed import get_ohlcv, check_all_feeds, FeedHealthError
from data.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


MOCK_OHLCV_RAW = [
    [1709510400000, 62000.0, 62500.0, 61800.0, 62300.0, 1500.0],
    [1709510700000, 62300.0, 62800.0, 62100.0, 62600.0, 1200.0],
    [1709511000000, 62600.0, 62900.0, 62400.0, 62700.0, 1100.0],
]

# Binance klines format (has extra fields after volume)
MOCK_BINANCE_KLINES = [
    [1709510400000, "62000.0", "62500.0", "61800.0", "62300.0", "1500.0", 0, "0", 0, "0", "0", "0"],
    [1709510700000, "62300.0", "62800.0", "62100.0", "62600.0", "1200.0", 0, "0", 0, "0", "0", "0"],
    [1709511000000, "62600.0", "62900.0", "62400.0", "62700.0", "1100.0", 0, "0", 0, "0", "0", "0"],
]


def _mock_httpx_response(data):
    """Create a mock httpx response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_get_ohlcv_returns_dataframe():
    """Verify OHLCV returns a properly structured DataFrame."""
    mock_resp = _mock_httpx_response(MOCK_BINANCE_KLINES)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("data.price_feed.httpx.AsyncClient", return_value=mock_client):
        df = await get_ohlcv("BTC", "5m", limit=3)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df["open"].iloc[0] == 62000.0
    assert df["close"].iloc[-1] == 62700.0


@pytest.mark.asyncio
async def test_get_ohlcv_timestamp_is_datetime():
    """Verify timestamp column is datetime type."""
    mock_resp = _mock_httpx_response(MOCK_BINANCE_KLINES)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("data.price_feed.httpx.AsyncClient", return_value=mock_client):
        df = await get_ohlcv("BTC", "15m", limit=3)

    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


@pytest.mark.asyncio
async def test_get_ohlcv_uses_cache():
    """Second call should return cached data without hitting API."""
    mock_resp = _mock_httpx_response(MOCK_BINANCE_KLINES)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("data.price_feed.httpx.AsyncClient", return_value=mock_client):
        df1 = await get_ohlcv("BTC", "5m", limit=3)
        df2 = await get_ohlcv("BTC", "5m", limit=3)

    # Only one API call (second hits cache)
    assert mock_client.get.call_count == 1
    pd.testing.assert_frame_equal(df1, df2)


@pytest.mark.asyncio
async def test_get_ohlcv_fallback_to_coinbase():
    """If Binance fails, should fall back to Coinbase."""
    # Binance fails
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("binance down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Coinbase succeeds
    mock_coinbase = AsyncMock()
    mock_coinbase.fetch_ohlcv = AsyncMock(return_value=MOCK_OHLCV_RAW)
    mock_coinbase.close = AsyncMock()

    with patch("data.price_feed.httpx.AsyncClient", return_value=mock_client), \
         patch("data.price_feed.ccxt_async.coinbase", return_value=mock_coinbase):
        df = await get_ohlcv("ETH", "1h", limit=3)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3


@pytest.mark.asyncio
async def test_get_ohlcv_unknown_asset():
    """Should raise ValueError for unknown asset."""
    with pytest.raises(ValueError, match="Unknown timeframe"):
        await get_ohlcv("BTC", "99m")


@pytest.mark.asyncio
async def test_get_ohlcv_unknown_timeframe():
    """Should raise ValueError for unknown timeframe."""
    with pytest.raises(ValueError, match="Unknown timeframe"):
        await get_ohlcv("BTC", "99m")


@pytest.mark.asyncio
async def test_get_ohlcv_all_exchanges_fail():
    """If all exchanges fail, should raise RuntimeError."""
    # Binance fails
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("binance down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Coinbase also fails
    mock_coinbase = AsyncMock()
    mock_coinbase.fetch_ohlcv = AsyncMock(side_effect=Exception("coinbase down"))
    mock_coinbase.close = AsyncMock()

    with patch("data.price_feed.httpx.AsyncClient", return_value=mock_client), \
         patch("data.price_feed.ccxt_async.coinbase", return_value=mock_coinbase):
        with pytest.raises(RuntimeError, match="Failed to fetch OHLCV"):
            await get_ohlcv("BTC", "5m")


@pytest.mark.asyncio
async def test_get_ohlcv_volume_column():
    """Verify volume data is present and correct."""
    mock_resp = _mock_httpx_response(MOCK_BINANCE_KLINES)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("data.price_feed.httpx.AsyncClient", return_value=mock_client):
        df = await get_ohlcv("SOL", "4h", limit=3)

    assert df["volume"].iloc[0] == 1500.0


class TestFeedHealth:
    @pytest.mark.asyncio
    async def test_check_all_feeds_passes(self):
        """All feeds working → returns dict with all True."""
        mock_resp = _mock_httpx_response(MOCK_BINANCE_KLINES)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("data.price_feed.httpx.AsyncClient", return_value=mock_client):
            result = await check_all_feeds()

        assert all(result.values())
        assert set(result.keys()) == {"BTC", "ETH", "SOL", "XRP"}

    @pytest.mark.asyncio
    async def test_check_all_feeds_raises_on_failure(self):
        """Any feed broken → raises FeedHealthError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_coinbase = AsyncMock()
        mock_coinbase.fetch_ohlcv = AsyncMock(side_effect=Exception("also down"))
        mock_coinbase.close = AsyncMock()

        with patch("data.price_feed.httpx.AsyncClient", return_value=mock_client), \
             patch("data.price_feed.ccxt_async.coinbase", return_value=mock_coinbase):
            with pytest.raises(FeedHealthError, match="STARTUP HEALTH CHECK FAILED"):
                await check_all_feeds()

    def test_feed_health_error_is_exception(self):
        """FeedHealthError is a proper Exception subclass."""
        err = FeedHealthError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"
