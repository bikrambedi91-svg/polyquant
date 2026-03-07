"""Binance Futures funding rate feed."""

import httpx
import structlog

from data.cache import cache
from config.constants import CACHE_TTL

logger = structlog.get_logger(__name__)

BINANCE_FAPI_BASE = "https://fapi.binance.com"
FUNDING_ENDPOINT = "/fapi/v1/fundingRate"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0


async def get_funding(asset: str) -> dict:
    """Fetch the latest funding rate for an asset from Binance Futures.

    Returns:
        {"rate": float, "timestamp": int, "asset": str}

    On failure after retries, returns {"rate": 0.0, "timestamp": 0, "asset": asset}
    with a warning log.
    """
    cache_key = f"funding:{asset}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    symbol = f"{asset}USDT"
    url = f"{BINANCE_FAPI_BASE}{FUNDING_ENDPOINT}"
    params = {"symbol": symbol, "limit": 1}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            if not data:
                logger.warning("funding_empty_response", asset=asset)
                return {"rate": 0.0, "timestamp": 0, "asset": asset}

            entry = data[0]
            result = {
                "rate": float(entry["fundingRate"]),
                "timestamp": int(entry["fundingTime"]),
                "asset": asset,
            }
            cache.set(cache_key, result, CACHE_TTL["funding"])
            logger.info("funding_fetched", asset=asset, rate=result["rate"])
            return result

        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.error("funding_fetch_failed", asset=asset, error=str(exc))
                return {"rate": 0.0, "timestamp": 0, "asset": asset}

            import asyncio

            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "funding_fetch_retry",
                asset=asset,
                attempt=attempt,
                delay=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)

    return {"rate": 0.0, "timestamp": 0, "asset": asset}
