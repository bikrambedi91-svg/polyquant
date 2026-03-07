"""Polymarket market discovery — deterministic slug-based UP/DOWN market scanner.

Generates deterministic slugs for all 12 active UP/DOWN markets
(4 assets × 3 timeframes: 15m, 1h, 4h) and looks them up directly
via the Gamma API events/slug endpoint. No pagination needed.

Slug formats:
  15m: {asset}-updown-15m-{unix_ts}    (ts aligned to 900s boundaries)
  1h:  {asset_full}-up-or-down-{month}-{day}-{hour}{ampm}-et
  4h:  {asset}-updown-4h-{unix_ts}     (ts aligned to 4h ET blocks)
"""

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import structlog

from config.constants import GAMMA_API_BASE

logger = structlog.get_logger(__name__)

ET = ZoneInfo("America/New_York")

# Asset slug mappings
ASSET_SLUG_SHORT = {"BTC": "btc", "ETH": "eth", "SOL": "sol", "XRP": "xrp"}
ASSET_SLUG_FULL = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "xrp"}

# Asset name patterns for identifying asset from question text
ASSET_PATTERNS: dict[str, list[str]] = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
    "XRP": ["xrp", "ripple"],
}

TRADEABLE_TIMEFRAMES = ["15m", "1h", "4h"]

# Minimum time-to-resolution (seconds) per timeframe
MIN_TTR: dict[str, int] = {
    "15m": 300,     # 5 min
    "1h": 900,      # 15 min
    "4h": 1800,     # 30 min
}

# Maximum time-to-resolution (seconds)
MAX_TTR: dict[str, int] = {
    "15m": 1800,    # 30 min
    "1h": 7200,     # 2 hours
    "4h": 21600,    # 6 hours
}

# Maximum time since start for UP/DOWN markets (seconds)
MAX_MARKET_AGE: dict[str, int] = {
    "15m": 300,     # 5 min
    "1h": 2400,     # 40 min (enables re-entries)
    "4h": 1800,     # 30 min
}

# Interval durations in seconds
TF_DURATIONS: dict[str, int] = {
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
}


@dataclass
class CryptoMarket:
    """Represents a discovered Polymarket crypto market."""
    title: str
    url: str
    token_id_yes: str
    token_id_no: str
    asset: str
    market_type: str           # "up_down"
    timeframe: str             # "15m", "1h", "4h"
    volume: float
    end_datetime: datetime | None
    start_datetime: datetime | None = None
    resolution_source: str = "chainlink_oracle"
    current_yes_price: float = 0.5
    condition_id: str = ""
    question: str = ""


class PolymarketScanner:
    """Discovers active crypto UP/DOWN markets using deterministic slug generation.

    Generates the exact slug for each of the 12 current markets and looks them
    up directly — no pagination, no text classification, no guessing.
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._client = http_client

    async def discover_markets(self) -> list[CryptoMarket]:
        """Generate slugs for all 12 current markets and fetch them."""
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=15)
        try:
            slugs = self._generate_all_slugs()
            markets: list[CryptoMarket] = []

            for asset, timeframe, slug in slugs:
                try:
                    market = await self._fetch_by_slug(client, asset, timeframe, slug)
                    if market and self._passes_filters(market):
                        markets.append(market)
                except Exception as exc:
                    logger.warning(
                        "slug_fetch_error",
                        slug=slug,
                        error=str(exc),
                    )

            logger.info(
                "markets_discovered",
                total=len(markets),
                by_tf={
                    tf: sum(1 for m in markets if m.timeframe == tf)
                    for tf in TRADEABLE_TIMEFRAMES
                },
            )
            return markets

        except Exception as exc:
            logger.error("market_discovery_error", error=str(exc))
            return []
        finally:
            if owns_client:
                await client.aclose()

    def _generate_all_slugs(self) -> list[tuple[str, str, str]]:
        """Generate (asset, timeframe, slug) tuples for all 12 current markets."""
        now_unix = time.time()
        now_utc = datetime.fromtimestamp(now_unix, tz=timezone.utc)
        dt_et = now_utc.astimezone(ET)
        result: list[tuple[str, str, str]] = []

        for asset in ASSET_SLUG_SHORT:
            # 15m: aligned to 900s boundaries
            ts_15m = int(now_unix // 900) * 900
            slug_15m = f"{ASSET_SLUG_SHORT[asset]}-updown-15m-{ts_15m}"
            result.append((asset, "15m", slug_15m))

            # 1h: human-readable ET format
            dt_floor = dt_et.replace(minute=0, second=0, microsecond=0)
            month = dt_floor.strftime("%B").lower()
            day = dt_floor.day
            hour_12 = dt_floor.strftime("%I").lstrip("0")
            ampm = dt_floor.strftime("%p").lower()
            slug_1h = f"{ASSET_SLUG_FULL[asset]}-up-or-down-{month}-{day}-{hour_12}{ampm}-et"
            result.append((asset, "1h", slug_1h))

            # 4h: aligned to 4h blocks in ET (0, 4, 8, 12, 16, 20)
            block_hour = (dt_et.hour // 4) * 4
            block_start_et = dt_et.replace(hour=block_hour, minute=0, second=0, microsecond=0)
            ts_4h = int(block_start_et.astimezone(timezone.utc).timestamp())
            slug_4h = f"{ASSET_SLUG_SHORT[asset]}-updown-4h-{ts_4h}"
            result.append((asset, "4h", slug_4h))

        return result

    async def _fetch_by_slug(
        self,
        client: httpx.AsyncClient,
        asset: str,
        timeframe: str,
        slug: str,
    ) -> CryptoMarket | None:
        """Fetch a single market by its deterministic slug."""
        url = f"{GAMMA_API_BASE}/events/slug/{slug}"
        resp = await client.get(url)

        if resp.status_code == 404:
            logger.debug("slug_not_found", slug=slug)
            return None

        resp.raise_for_status()
        event = resp.json()

        event_markets = event.get("markets", [])
        if not event_markets:
            return None

        mkt = event_markets[0]
        return self._parse_market(mkt, asset, timeframe, slug)

    def _parse_market(
        self,
        mkt: dict,
        asset: str,
        timeframe: str,
        slug: str,
    ) -> CryptoMarket | None:
        """Parse a single market from Gamma API event response."""
        if mkt.get("closed") or not mkt.get("acceptingOrders", True):
            return None

        question = mkt.get("question", "")

        # Parse token IDs (stringified JSON)
        clob_token_ids_raw = mkt.get("clobTokenIds", "")
        if isinstance(clob_token_ids_raw, str):
            try:
                clob_token_ids = json.loads(clob_token_ids_raw)
            except (json.JSONDecodeError, ValueError):
                return None
        else:
            clob_token_ids = clob_token_ids_raw
        if not isinstance(clob_token_ids, list) or len(clob_token_ids) < 2:
            return None

        # Parse outcome prices (stringified JSON)
        current_yes_price = 0.5
        outcome_prices_raw = mkt.get("outcomePrices", "")
        if outcome_prices_raw:
            try:
                prices = json.loads(outcome_prices_raw)
                if prices and len(prices) >= 1:
                    current_yes_price = float(prices[0])
            except (json.JSONDecodeError, ValueError, IndexError):
                pass

        # Parse end datetime
        end_date_str = mkt.get("endDate", "")
        end_datetime = self._parse_end_date(end_date_str)

        # Compute start_datetime from known duration
        start_datetime = None
        if end_datetime:
            duration = TF_DURATIONS.get(timeframe, 0)
            if duration > 0:
                start_datetime = end_datetime - timedelta(seconds=duration)

        volume = float(mkt.get("volume", 0) or 0)
        condition_id = mkt.get("conditionId", "")
        market_url = f"https://polymarket.com/event/{slug}"

        return CryptoMarket(
            title=question,
            url=market_url,
            token_id_yes=clob_token_ids[0],
            token_id_no=clob_token_ids[1],
            asset=asset,
            market_type="up_down",
            timeframe=timeframe,
            volume=volume,
            end_datetime=end_datetime,
            start_datetime=start_datetime,
            current_yes_price=current_yes_price,
            condition_id=condition_id,
            question=question,
        )

    def _parse_end_date(self, end_date_str: str) -> datetime | None:
        """Parse ISO 8601 end date string."""
        if not end_date_str:
            return None
        try:
            end_date_str = end_date_str.replace("Z", "+00:00")
            return datetime.fromisoformat(end_date_str)
        except (ValueError, TypeError):
            return None

    def _passes_filters(self, market: CryptoMarket) -> bool:
        """Basic filter — only reject expired or non-accepting markets.

        Trading filters (MIN_TTR, MAX_MARKET_AGE) are applied by the pipeline
        at trade entry time, not here. The scanner's job is to discover all 12
        current markets so they're always visible in the dashboard.
        """
        if not market.end_datetime:
            return False

        now = datetime.now(timezone.utc)
        ttr = (market.end_datetime - now).total_seconds()

        # Only reject if already expired
        if ttr <= 0:
            return False

        return True

    def _identify_asset(self, question: str) -> str | None:
        """Return asset code if question mentions a tradeable asset."""
        q_lower = question.lower()
        for asset, patterns in ASSET_PATTERNS.items():
            for pattern in patterns:
                if pattern in q_lower:
                    return asset
        return None
