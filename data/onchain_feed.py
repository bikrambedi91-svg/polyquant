"""Exchange net flow feed (on-chain data).

Tries CryptoQuant if API key is provided. Otherwise returns neutral mock data
with confidence=0, which causes the ensemble to give ChainFlow model zero
effective weight.
"""

import httpx
import structlog

from data.cache import cache
from config.constants import CACHE_TTL

logger = structlog.get_logger(__name__)

CRYPTOQUANT_BASE = "https://api.cryptoquant.com/v1"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0


def _neutral_result(asset: str) -> dict:
    """Return a neutral result with zero confidence (effectively disables this signal)."""
    return {"net_flow": 0.0, "confidence": 0, "asset": asset}


async def get_exchange_flow(asset: str, api_key: str | None = None) -> dict:
    """Fetch exchange net flow data for an asset.

    Returns:
        {"net_flow": float, "confidence": int (0-100), "asset": str}

    When confidence=0, the ensemble gives this model zero effective weight.
    Without a CryptoQuant API key, always returns neutral data.
    """
    if not api_key:
        logger.debug("onchain_no_api_key", asset=asset)
        return _neutral_result(asset)

    cache_key = f"onchain:{asset}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # CryptoQuant exchange flow endpoint
    asset_lower = asset.lower()
    url = f"{CRYPTOQUANT_BASE}/btc/exchange-flows/netflow"  # BTC-specific
    if asset_lower != "btc":
        # CryptoQuant has limited altcoin coverage — return neutral for non-BTC
        logger.debug("onchain_no_altcoin_support", asset=asset)
        return _neutral_result(asset)

    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers, params={"window": "hour", "limit": 1})
                resp.raise_for_status()
                data = resp.json()

            if not data.get("result", {}).get("data"):
                logger.warning("onchain_empty_response", asset=asset)
                return _neutral_result(asset)

            entry = data["result"]["data"][0]
            net_flow = float(entry.get("netflow", 0.0))
            result = {"net_flow": net_flow, "confidence": 60, "asset": asset}

            cache.set(cache_key, result, CACHE_TTL["onchain"])
            logger.info("onchain_fetched", asset=asset, net_flow=net_flow)
            return result

        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.error("onchain_fetch_failed", asset=asset, error=str(exc))
                return _neutral_result(asset)

            import asyncio

            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning("onchain_fetch_retry", asset=asset, attempt=attempt, error=str(exc))
            await asyncio.sleep(delay)

    return _neutral_result(asset)
