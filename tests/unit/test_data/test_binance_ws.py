"""Tests for data/binance_ws.py — Binance WebSocket kline + trade streams."""

import asyncio
import json
import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from data.binance_ws import BinanceWSManager, MAX_KLINE_BUFFER, TRADE_WINDOW_S


@pytest.fixture
def ws_manager():
    """Create a WS manager for testing."""
    mgr = BinanceWSManager(
        assets=["BTC", "ETH"],
        timeframes=["15m", "1h"],
    )
    return mgr


# ── Initialization Tests ──


def test_init_defaults():
    """Default init covers all 4 assets and 3 timeframes."""
    mgr = BinanceWSManager()
    assert set(mgr._assets) == {"BTC", "ETH", "SOL", "XRP"}
    assert set(mgr._timeframes) == {"15m", "1h", "4h"}
    assert not mgr.connected


def test_init_custom(ws_manager):
    """Custom assets/timeframes are stored correctly."""
    assert ws_manager._assets == ["BTC", "ETH"]
    assert ws_manager._timeframes == ["15m", "1h"]


def test_buffers_initialized(ws_manager):
    """Kline and trade buffers should be pre-initialized."""
    assert ("BTC", "15m") in ws_manager._kline_buffer
    assert ("ETH", "1h") in ws_manager._kline_buffer
    assert "BTC" in ws_manager._recent_trades
    assert "ETH" in ws_manager._recent_trades


# ── Stream URL Tests ──


def test_build_stream_url(ws_manager):
    """Stream URL should contain all kline + trade streams."""
    url = ws_manager._build_stream_url()
    assert "wss://stream.binance.com:9443/stream?streams=" in url
    assert "btcusdt@kline_15m" in url
    assert "btcusdt@kline_1h" in url
    assert "btcusdt@trade" in url
    assert "ethusdt@kline_15m" in url
    assert "ethusdt@trade" in url


def test_stream_url_uses_slash_separator(ws_manager):
    """Streams should be separated by /."""
    url = ws_manager._build_stream_url()
    streams_part = url.split("?streams=")[1]
    streams = streams_part.split("/")
    # 2 assets × (2 timeframes + 1 trade) = 6 streams
    assert len(streams) == 6


# ── Kline Handling Tests ──


@pytest.mark.asyncio
async def test_handle_kline_open(ws_manager):
    """Open kline (x=false) should update current_kline but not buffer."""
    data = {
        "k": {
            "s": "BTCUSDT",
            "i": "1h",
            "t": 1709510400000,
            "o": "62000.0",
            "h": "62500.0",
            "l": "61800.0",
            "c": "62300.0",
            "v": "1500.0",
            "x": False,
        }
    }
    await ws_manager._handle_kline(data)

    assert ("BTC", "1h") in ws_manager._current_kline
    candle = ws_manager._current_kline[("BTC", "1h")]
    assert candle[0] == 1709510400000
    assert candle[1] == 62000.0
    assert candle[4] == 62300.0
    # Buffer should still be empty (not closed)
    assert len(ws_manager._kline_buffer[("BTC", "1h")]) == 0


@pytest.mark.asyncio
async def test_handle_kline_closed(ws_manager):
    """Closed kline (x=true) should push to buffer."""
    data = {
        "k": {
            "s": "BTCUSDT",
            "i": "15m",
            "t": 1709510400000,
            "o": "62000.0",
            "h": "62500.0",
            "l": "61800.0",
            "c": "62300.0",
            "v": "1500.0",
            "x": True,
        }
    }
    await ws_manager._handle_kline(data)

    buf = ws_manager._kline_buffer[("BTC", "15m")]
    assert len(buf) == 1
    assert buf[0][1] == 62000.0


@pytest.mark.asyncio
async def test_handle_kline_unknown_symbol(ws_manager):
    """Unknown symbol should be silently ignored."""
    data = {
        "k": {
            "s": "DOGEUSDT",
            "i": "1h",
            "t": 1709510400000,
            "o": "0.1",
            "h": "0.2",
            "l": "0.05",
            "c": "0.15",
            "v": "1000.0",
            "x": True,
        }
    }
    await ws_manager._handle_kline(data)
    # No crash, no data stored
    assert ws_manager.get_cached_ohlcv("DOGE", "1h") is None


# ── Trade Handling Tests ──


@pytest.mark.asyncio
async def test_handle_trade(ws_manager):
    """Trade event should update last price and trade buffer."""
    data = {
        "s": "ETHUSDT",
        "p": "3100.50",
        "q": "2.5",
        "T": int(time.time() * 1000),
        "m": False,
    }
    await ws_manager._handle_trade(data)

    assert ws_manager._last_price["ETH"] == 3100.50
    assert len(ws_manager._recent_trades["ETH"]) == 1
    assert ws_manager._recent_trades["ETH"][0]["price"] == 3100.50


@pytest.mark.asyncio
async def test_get_latest_price(ws_manager):
    """get_latest_price should return last trade price."""
    data = {
        "s": "BTCUSDT",
        "p": "65000.0",
        "q": "0.1",
        "T": int(time.time() * 1000),
        "m": True,
    }
    await ws_manager._handle_trade(data)

    assert ws_manager.get_latest_price("BTC") == 65000.0
    assert ws_manager.get_latest_price("SOL") is None  # Not in this manager


# ── Recent Trades Window Tests ──


@pytest.mark.asyncio
async def test_get_recent_trades_window(ws_manager):
    """Only trades within the window should be returned."""
    now_ms = int(time.time() * 1000)

    # Old trade (3 minutes ago — outside 120s window)
    old_trade = {"s": "BTCUSDT", "p": "60000", "q": "1", "T": now_ms - 180000, "m": False}
    await ws_manager._handle_trade(old_trade)

    # Recent trade (10 seconds ago)
    recent_trade = {"s": "BTCUSDT", "p": "61000", "q": "0.5", "T": now_ms - 10000, "m": True}
    await ws_manager._handle_trade(recent_trade)

    trades = ws_manager.get_recent_trades("BTC", window_s=120)
    assert len(trades) == 1
    assert trades[0]["price"] == 61000.0


# ── Cached OHLCV Tests ──


@pytest.mark.asyncio
async def test_get_cached_ohlcv_empty(ws_manager):
    """No data → None."""
    assert ws_manager.get_cached_ohlcv("BTC", "1h") is None


@pytest.mark.asyncio
async def test_get_cached_ohlcv_with_data(ws_manager):
    """After closed candles, should return a DataFrame."""
    # Push 3 closed candles
    for i in range(3):
        data = {
            "k": {
                "s": "BTCUSDT",
                "i": "1h",
                "t": 1709510400000 + i * 3600000,
                "o": str(62000 + i * 100),
                "h": str(62500 + i * 100),
                "l": str(61800 + i * 100),
                "c": str(62300 + i * 100),
                "v": str(1500 - i * 100),
                "x": True,
            }
        }
        await ws_manager._handle_kline(data)

    df = ws_manager.get_cached_ohlcv("BTC", "1h")
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df["open"].iloc[0] == 62000.0


@pytest.mark.asyncio
async def test_get_cached_ohlcv_includes_current(ws_manager):
    """Current open candle should be appended to closed candles."""
    # 1 closed candle
    closed = {
        "k": {
            "s": "ETHUSDT", "i": "15m", "t": 1709510400000,
            "o": "3000", "h": "3050", "l": "2980", "c": "3020", "v": "500",
            "x": True,
        }
    }
    await ws_manager._handle_kline(closed)

    # 1 open candle (different timestamp)
    open_k = {
        "k": {
            "s": "ETHUSDT", "i": "15m", "t": 1709511300000,
            "o": "3020", "h": "3060", "l": "3010", "c": "3040", "v": "200",
            "x": False,
        }
    }
    await ws_manager._handle_kline(open_k)

    df = ws_manager.get_cached_ohlcv("ETH", "15m")
    assert len(df) == 2  # 1 closed + 1 open
    assert df["open"].iloc[1] == 3020.0


# ── Message Routing Tests ──


@pytest.mark.asyncio
async def test_on_message_routes_kline(ws_manager):
    """Combined stream kline message should be routed correctly."""
    msg = {
        "stream": "btcusdt@kline_1h",
        "data": {
            "k": {
                "s": "BTCUSDT", "i": "1h", "t": 1709510400000,
                "o": "62000", "h": "62500", "l": "61800", "c": "62300", "v": "1500",
                "x": False,
            }
        }
    }
    await ws_manager._on_message(msg)
    assert ("BTC", "1h") in ws_manager._current_kline


@pytest.mark.asyncio
async def test_on_message_routes_trade(ws_manager):
    """Combined stream trade message should be routed correctly."""
    msg = {
        "stream": "ethusdt@trade",
        "data": {
            "s": "ETHUSDT", "p": "3100", "q": "1", "T": int(time.time() * 1000), "m": False,
        }
    }
    await ws_manager._on_message(msg)
    assert ws_manager._last_price["ETH"] == 3100.0


@pytest.mark.asyncio
async def test_on_message_ignores_empty(ws_manager):
    """Empty or malformed messages should be silently ignored."""
    await ws_manager._on_message({})
    await ws_manager._on_message({"stream": "", "data": {}})
    await ws_manager._on_message({"stream": "unknown@thing", "data": {"foo": "bar"}})
    # No crash


# ── Status Tests ──


def test_get_status(ws_manager):
    """Status dict should have all expected keys."""
    status = ws_manager.get_status()
    assert "connected" in status
    assert "running" in status
    assert "last_prices" in status
    assert "kline_counts" in status
    assert "trade_buffer_sizes" in status
    assert status["connected"] is False
    assert status["running"] is False


# ── Cache Push Tests ──


@pytest.mark.asyncio
async def test_closed_kline_pushes_to_cache(ws_manager):
    """Closed kline should push data to the TTL cache."""
    from data.cache import cache
    cache.clear()

    data = {
        "k": {
            "s": "BTCUSDT", "i": "1h", "t": 1709510400000,
            "o": "62000", "h": "62500", "l": "61800", "c": "62300", "v": "1500",
            "x": True,
        }
    }
    await ws_manager._handle_kline(data)

    cached = cache.get("ohlcv:BTC:1h:100")
    assert cached is not None
    assert isinstance(cached, pd.DataFrame)
    assert len(cached) == 1

    cache.clear()


# ── Start/Stop Tests ──


@pytest.mark.asyncio
async def test_start_stop_lifecycle(ws_manager):
    """Start should set running, stop should clear it."""
    with patch("data.binance_ws.websockets.connect", new_callable=AsyncMock) as mock_connect:
        # Make connect raise to exit the loop immediately
        mock_connect.side_effect = asyncio.CancelledError()

        await ws_manager.start()
        assert ws_manager._running is True

        await ws_manager.stop()
        assert ws_manager._running is False
        assert ws_manager._connected is False
