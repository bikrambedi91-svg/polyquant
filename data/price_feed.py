"""Async OHLCV price feed — Binance primary (direct API), Coinbase fallback (ccxt).

Binance uses direct httpx calls to /api/v3/klines to avoid ccxt's load_markets()
which downloads a 16MB exchangeInfo response and times out.
Coinbase fallback uses ccxt with the 'coinbase' exchange (not 'coinbasepro').

If BOTH Binance and Coinbase fail for an asset, the bot must halt — never trade blind.
"""

import asyncio
import structlog
import pandas as pd
import httpx
import ccxt.async_support as ccxt_async

from config.constants import (
    ASSET_SYMBOLS,
    CCXT_TIMEFRAMES,
    CACHE_TTL,
)
from data.cache import cache


class FeedHealthError(Exception):
    """Raised when price feeds are critically broken — bot must stop."""
    pass

logger = structlog.get_logger(__name__)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

# Map our assets to Binance symbol format (no slash)
BINANCE_SYMBOLS: dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT",
}

# Coinbase uses different pair format
COINBASE_SYMBOLS: dict[str, str] = {
    "BTC": "BTC/USDT",
    "ETH": "ETH/USDT",
    "SOL": "SOL/USDT",
    "XRP": "XRP/USDT",
}


async def _fetch_binance_klines(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    limit: int,
) -> list[list]:
    """Fetch OHLCV from Binance klines API directly (no ccxt, no load_markets)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(
                BINANCE_KLINES_URL,
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
            resp.raise_for_status()
            raw = resp.json()
            # Binance klines format: [open_time, open, high, low, close, volume, ...]
            # Convert to ccxt-compatible: [timestamp_ms, open, high, low, close, volume]
            return [
                [int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]
                for k in raw
            ]
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "ohlcv_fetch_retry",
                exchange="binance",
                symbol=symbol,
                attempt=attempt,
                delay=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)
    return []


async def _fetch_coinbase_ohlcv(
    symbol: str,
    timeframe: str,
    limit: int,
) -> list[list]:
    """Fetch OHLCV from Coinbase via ccxt as fallback."""
    exchange = ccxt_async.coinbase({"enableRateLimit": True, "timeout": 30000})
    try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                data = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                return data
            except Exception as exc:
                if attempt == MAX_RETRIES:
                    raise
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "ohlcv_fetch_retry",
                    exchange="coinbase",
                    symbol=symbol,
                    attempt=attempt,
                    delay=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
    finally:
        await exchange.close()
    return []


async def get_ohlcv(
    asset: str,
    timeframe: str,
    limit: int = 100,
    api_key: str = "",
    api_secret: str = "",
) -> pd.DataFrame:
    """Fetch OHLCV candles for an asset and timeframe.

    Returns a DataFrame with columns:
        [timestamp, open, high, low, close, volume]

    Uses in-memory cache. Tries Binance direct API first, Coinbase ccxt fallback.
    """
    cache_key = f"ohlcv:{asset}:{timeframe}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    ccxt_tf = CCXT_TIMEFRAMES.get(timeframe)
    if ccxt_tf is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    raw: list[list] = []
    source = ""

    # Primary: Binance direct klines API
    binance_sym = BINANCE_SYMBOLS.get(asset)
    if binance_sym:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                raw = await _fetch_binance_klines(client, binance_sym, ccxt_tf, limit)
            if raw:
                source = "binance"
        except Exception as exc:
            logger.warning("ohlcv_exchange_failed", exchange="binance", error=str(exc))

    # Fallback: Coinbase via ccxt
    if not raw:
        coinbase_sym = COINBASE_SYMBOLS.get(asset)
        if coinbase_sym:
            try:
                raw = await _fetch_coinbase_ohlcv(coinbase_sym, ccxt_tf, limit)
                if raw:
                    source = "coinbase"
            except Exception as exc:
                logger.warning("ohlcv_exchange_failed", exchange="coinbase", error=str(exc))

    if not raw:
        logger.error("ohlcv_all_exchanges_failed", asset=asset, timeframe=timeframe)
        raise RuntimeError(f"Failed to fetch OHLCV for {asset}/{timeframe} from all exchanges")

    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

    ttl_key = f"ohlcv_{timeframe}"
    ttl = CACHE_TTL.get(ttl_key, 60)
    cache.set(cache_key, df, ttl)

    logger.info("ohlcv_fetched", exchange=source, asset=asset, timeframe=timeframe, rows=len(df))
    return df


async def check_all_feeds() -> dict[str, bool]:
    """Startup health check — verify Binance (or Coinbase fallback) works for all assets.

    Returns {asset: True/False}. Raises FeedHealthError if ANY asset fails.
    """
    results: dict[str, bool] = {}
    failed: list[str] = []

    for asset in BINANCE_SYMBOLS:
        try:
            df = await get_ohlcv(asset, "1h", limit=5)
            ok = df is not None and len(df) > 0
            results[asset] = ok
            if ok:
                logger.info("feed_health_ok", asset=asset)
            else:
                failed.append(asset)
                results[asset] = False
        except Exception as exc:
            results[asset] = False
            failed.append(asset)
            logger.error("feed_health_failed", asset=asset, error=str(exc))

    if failed:
        raise FeedHealthError(
            f"STARTUP HEALTH CHECK FAILED: No price data for {failed}. "
            f"Both Binance and Coinbase are down. Bot will NOT start."
        )

    logger.info("feed_health_check_passed", results=results)
    return results
