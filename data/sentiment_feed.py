"""Fear & Greed Index feed from Alternative.me.

NOTE: This data updates ONCE PER DAY. It is useless for 5m/15m decisions.
The SentimentComp model has weight=0 on 5m/15m timeframes for this reason.
"""

import httpx
import structlog

from data.cache import cache
from config.constants import CACHE_TTL

logger = structlog.get_logger(__name__)

FNG_URL = "https://api.alternative.me/fng/"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0


async def get_fear_greed() -> dict:
    """Fetch the current Fear & Greed Index.

    Returns:
        {"value": int (0-100), "classification": str, "timestamp": str}

    0-24 = Extreme Fear, 25-49 = Fear, 50 = Neutral,
    51-74 = Greed, 75-100 = Extreme Greed.

    On failure, returns {"value": 50, "classification": "Neutral", "timestamp": ""}
    (neutral — neither fear nor greed).
    """
    cache_key = "sentiment:fng"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(FNG_URL, params={"limit": 1, "format": "json"})
                resp.raise_for_status()
                data = resp.json()

            entries = data.get("data", [])
            if not entries:
                logger.warning("sentiment_empty_response")
                return {"value": 50, "classification": "Neutral", "timestamp": ""}

            entry = entries[0]
            result = {
                "value": int(entry["value"]),
                "classification": entry.get("value_classification", "Unknown"),
                "timestamp": entry.get("timestamp", ""),
            }

            cache.set(cache_key, result, CACHE_TTL["sentiment"])
            logger.info("sentiment_fetched", value=result["value"], classification=result["classification"])
            return result

        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.error("sentiment_fetch_failed", error=str(exc))
                return {"value": 50, "classification": "Neutral", "timestamp": ""}

            import asyncio

            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning("sentiment_fetch_retry", attempt=attempt, error=str(exc))
            await asyncio.sleep(delay)

    return {"value": 50, "classification": "Neutral", "timestamp": ""}
