"""Binance WebSocket manager — real-time kline + trade streams.

Connects to Binance's combined stream endpoint for all assets × timeframes.
Maintains in-memory buffers for latest klines and recent trades.
Auto-reconnects on disconnect with exponential backoff.

Used as a fast path before REST fallback in DataProvider.
"""

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone

import pandas as pd
import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from config.constants import CCXT_TIMEFRAMES, CACHE_TTL
from data.cache import cache
from data.price_feed import BINANCE_SYMBOLS

logger = structlog.get_logger(__name__)

BINANCE_WS_BASE = "wss://stream.binance.com:9443/stream"

MAX_RECONNECT_DELAY = 30
INITIAL_RECONNECT_DELAY = 1
MAX_KLINE_BUFFER = 100  # candles per (asset, timeframe)
MAX_TRADE_BUFFER = 500  # trades per asset
TRADE_WINDOW_S = 120    # rolling window for recent trades


class BinanceWSManager:
    """Manages a single combined WebSocket connection to Binance.

    Streams kline updates and individual trades for all configured
    assets and timeframes. Buffers data in memory for fast reads.
    """

    def __init__(
        self,
        assets: list[str] | None = None,
        timeframes: list[str] | None = None,
    ):
        self._assets = assets or list(BINANCE_SYMBOLS.keys())
        self._timeframes = timeframes or ["15m", "1h", "4h"]
        self._running = False
        self._connected = False
        self._ws = None
        self._task: asyncio.Task | None = None

        # Reverse map: "btcusdt" → "BTC"
        self._symbol_to_asset: dict[str, str] = {
            v.lower(): k for k, v in BINANCE_SYMBOLS.items()
        }

        # Kline buffer: {(asset, timeframe): deque of [ts, o, h, l, c, v]}
        self._kline_buffer: dict[tuple[str, str], deque] = {}
        # Current open kline per (asset, timeframe)
        self._current_kline: dict[tuple[str, str], list] = {}

        # Trade buffer: {asset: deque of {price, qty, time_ms, is_buyer_maker}}
        self._recent_trades: dict[str, deque] = {}
        # Last trade price per asset
        self._last_price: dict[str, float] = {}

        self._lock = asyncio.Lock()
        self._reconnect_count = 0

        # Initialize buffers
        for asset in self._assets:
            self._recent_trades[asset] = deque(maxlen=MAX_TRADE_BUFFER)
            for tf in self._timeframes:
                self._kline_buffer[(asset, tf)] = deque(maxlen=MAX_KLINE_BUFFER)

    @property
    def connected(self) -> bool:
        return self._connected

    def _build_stream_url(self) -> str:
        """Build combined stream URL for all subscriptions."""
        streams = []
        for asset in self._assets:
            symbol = BINANCE_SYMBOLS.get(asset)
            if not symbol:
                continue
            sym_lower = symbol.lower()

            # Kline streams per timeframe
            for tf in self._timeframes:
                binance_tf = CCXT_TIMEFRAMES.get(tf)
                if binance_tf:
                    streams.append(f"{sym_lower}@kline_{binance_tf}")

            # Trade stream
            streams.append(f"{sym_lower}@trade")

        return f"{BINANCE_WS_BASE}?streams={'/'.join(streams)}"

    async def start(self) -> None:
        """Start the WebSocket connection as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "ws_manager_started",
            assets=self._assets,
            timeframes=self._timeframes,
            stream_count=len(self._assets) * (len(self._timeframes) + 1),
        )

    async def stop(self) -> None:
        """Stop the WebSocket connection gracefully."""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        logger.info("ws_manager_stopped")

    async def _run_loop(self) -> None:
        """Main loop: connect, listen, reconnect on failure."""
        delay = INITIAL_RECONNECT_DELAY

        while self._running:
            try:
                url = self._build_stream_url()
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    self._connected = True
                    self._reconnect_count = 0
                    delay = INITIAL_RECONNECT_DELAY
                    logger.info("ws_connected", url=url[:80] + "...")

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw_msg)
                            await self._on_message(msg)
                        except json.JSONDecodeError:
                            logger.warning("ws_invalid_json")

            except asyncio.CancelledError:
                raise
            except ConnectionClosed as exc:
                self._connected = False
                logger.warning("ws_disconnected", code=exc.code, reason=str(exc.reason)[:100])
            except Exception as exc:
                self._connected = False
                logger.warning("ws_error", error=str(exc)[:200])

            if not self._running:
                break

            # Exponential backoff reconnect
            self._reconnect_count += 1
            logger.info("ws_reconnecting", delay=delay, attempt=self._reconnect_count)
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)

    async def _on_message(self, msg: dict) -> None:
        """Route incoming WebSocket message to appropriate handler."""
        # Combined stream format: {"stream": "btcusdt@kline_1h", "data": {...}}
        stream = msg.get("stream", "")
        data = msg.get("data", {})

        if not stream or not data:
            return

        if "@kline_" in stream:
            await self._handle_kline(data)
        elif "@trade" in stream:
            await self._handle_trade(data)

    async def _handle_kline(self, data: dict) -> None:
        """Process a kline/candlestick update."""
        k = data.get("k", {})
        if not k:
            return

        symbol = k.get("s", "").lower()
        asset = self._symbol_to_asset.get(symbol)
        if not asset:
            return

        interval = k.get("i", "")
        # Reverse-map Binance interval back to our timeframe
        tf = None
        for our_tf, binance_tf in CCXT_TIMEFRAMES.items():
            if binance_tf == interval:
                tf = our_tf
                break
        if not tf:
            return

        candle = [
            int(k["t"]),       # open time ms
            float(k["o"]),     # open
            float(k["h"]),     # high
            float(k["l"]),     # low
            float(k["c"]),     # close
            float(k["v"]),     # volume
        ]

        key = (asset, tf)

        async with self._lock:
            self._current_kline[key] = candle

            # If candle is closed, push to buffer and cache
            if k.get("x", False):
                self._kline_buffer[key].append(candle)
                self._push_to_cache(asset, tf)

    async def _handle_trade(self, data: dict) -> None:
        """Process an individual trade event."""
        symbol = data.get("s", "").lower()
        asset = self._symbol_to_asset.get(symbol)
        if not asset:
            return

        price = float(data.get("p", 0))
        qty = float(data.get("q", 0))
        time_ms = int(data.get("T", 0))
        is_buyer_maker = data.get("m", False)

        async with self._lock:
            self._last_price[asset] = price
            self._recent_trades[asset].append({
                "price": price,
                "qty": qty,
                "time_ms": time_ms,
                "is_buyer_maker": is_buyer_maker,
            })

    def _push_to_cache(self, asset: str, tf: str) -> None:
        """Push buffered klines to TTL cache (same keys as REST)."""
        key = (asset, tf)
        buf = self._kline_buffer.get(key)
        if not buf:
            return

        raw = list(buf)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

        cache_key = f"ohlcv:{asset}:{tf}:100"
        ttl_key = f"ohlcv_{tf}"
        ttl = CACHE_TTL.get(ttl_key, 60)
        cache.set(cache_key, df, ttl)

    def get_cached_ohlcv(self, asset: str, timeframe: str) -> pd.DataFrame | None:
        """Return buffered OHLCV data if available.

        Returns a DataFrame with same schema as REST: [timestamp, open, high, low, close, volume].
        Includes the current open candle appended to closed candles.
        Returns None if no data buffered yet.
        """
        key = (asset, timeframe)
        buf = self._kline_buffer.get(key)
        if not buf:
            return None

        raw = list(buf)

        # Append current open candle if available
        current = self._current_kline.get(key)
        if current:
            # Don't duplicate if the current candle is already in the buffer
            if not raw or raw[-1][0] != current[0]:
                raw.append(current)

        if not raw:
            return None

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def get_latest_price(self, asset: str) -> float | None:
        """Return the last trade price for an asset, or None."""
        return self._last_price.get(asset)

    def get_recent_trades(self, asset: str, window_s: int = TRADE_WINDOW_S) -> list[dict]:
        """Return trades within the last `window_s` seconds."""
        buf = self._recent_trades.get(asset)
        if not buf:
            return []

        cutoff_ms = int((time.time() - window_s) * 1000)
        return [t for t in buf if t["time_ms"] >= cutoff_ms]

    def get_status(self) -> dict:
        """Return status info for dashboard/logging."""
        kline_counts = {
            f"{a}:{tf}": len(self._kline_buffer.get((a, tf), []))
            for a in self._assets
            for tf in self._timeframes
        }
        return {
            "connected": self._connected,
            "running": self._running,
            "reconnect_count": self._reconnect_count,
            "last_prices": dict(self._last_price),
            "kline_counts": kline_counts,
            "trade_buffer_sizes": {
                a: len(self._recent_trades.get(a, []))
                for a in self._assets
            },
        }
