"""CLOB order book analysis — spread, depth, slippage, imbalance.

Uses py_clob_client for REST reads with short-TTL caching.
WebSocket subscription available for 5m/15m real-time updates.
"""

import time
from dataclasses import dataclass, field

import structlog

from data.cache import cache

logger = structlog.get_logger(__name__)

ORDERBOOK_CACHE_TTL = 5  # seconds


@dataclass
class OrderBookSnapshot:
    """Analyzed state of a CLOB order book."""
    token_id: str
    midpoint: float
    spread_cents: float
    spread_bps: float
    total_bid_size: float
    total_ask_size: float
    bid_ask_imbalance: float         # bid_size / ask_size (>1 = bid heavy)
    depth_at_1pct: float             # cumulative USD within 1% of mid
    depth_at_2pct: float
    depth_at_5pct: float
    avg_fill_price: float            # walk-the-book for intended size
    expected_slippage_cents: float   # avg_fill - mid
    sufficient_liquidity: bool
    best_bid: float = 0.0
    best_ask: float = 0.0
    bid_levels: int = 0
    ask_levels: int = 0


class OrderBookAnalyzer:
    """Analyzes Polymarket CLOB order books via py_clob_client."""

    def __init__(self, clob_client=None):
        """Initialize with optional ClobClient instance (for testing/DI)."""
        self._client = clob_client

    def _get_client(self):
        """Lazy-initialize ClobClient if not injected."""
        if self._client is None:
            from py_clob_client.client import ClobClient
            from config.constants import CLOB_API_BASE
            self._client = ClobClient(CLOB_API_BASE)
        return self._client

    async def analyze(
        self, token_id: str, intended_size_usd: float = 100.0
    ) -> OrderBookSnapshot:
        """Fetch and analyze the order book for a token.

        Args:
            token_id: CLOB token ID (YES or NO token)
            intended_size_usd: intended trade size for slippage calculation
        """
        # Check cache
        cache_key = f"orderbook:{token_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            # Recalculate slippage for the requested size
            return self._recalc_slippage(cached, intended_size_usd)

        client = self._get_client()
        try:
            import asyncio
            book = await asyncio.to_thread(client.get_order_book, token_id)
        except Exception as exc:
            logger.error("orderbook_fetch_error", token_id=token_id, error=str(exc))
            return self._empty_snapshot(token_id)

        bids = book.get("bids", []) if isinstance(book, dict) else getattr(book, "bids", [])
        asks = book.get("asks", []) if isinstance(book, dict) else getattr(book, "asks", [])

        # Normalize to list of (price, size) tuples
        bids_parsed = self._parse_levels(bids, descending=True)
        asks_parsed = self._parse_levels(asks, descending=False)

        snapshot = self._compute_snapshot(token_id, bids_parsed, asks_parsed, intended_size_usd)

        # Cache raw book data for re-analysis
        cache.set(cache_key, snapshot, ttl=ORDERBOOK_CACHE_TTL)

        return snapshot

    def _parse_levels(
        self, levels: list, descending: bool = False
    ) -> list[tuple[float, float]]:
        """Parse order book levels into (price, size) tuples."""
        parsed = []
        for level in levels:
            if isinstance(level, dict):
                price = float(level.get("price", 0))
                size = float(level.get("size", 0))
            elif hasattr(level, "price"):
                price = float(level.price)
                size = float(level.size)
            elif isinstance(level, (list, tuple)) and len(level) >= 2:
                price = float(level[0])
                size = float(level[1])
            else:
                continue
            if price > 0 and size > 0:
                parsed.append((price, size))

        parsed.sort(key=lambda x: x[0], reverse=descending)
        return parsed

    def _compute_snapshot(
        self,
        token_id: str,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        intended_size_usd: float,
    ) -> OrderBookSnapshot:
        """Compute all analytics from parsed bid/ask levels."""
        if not bids or not asks:
            return self._empty_snapshot(token_id)

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        midpoint = (best_bid + best_ask) / 2.0
        spread_cents = best_ask - best_bid
        spread_bps = (spread_cents / midpoint * 10_000) if midpoint > 0 else 0

        # Total sizes
        total_bid_size = sum(s for _, s in bids)
        total_ask_size = sum(s for _, s in asks)
        imbalance = total_bid_size / total_ask_size if total_ask_size > 0 else 0.0

        # Depth at 1%, 2%, 5% from midpoint
        depth_1 = self._cumulative_depth(bids, asks, midpoint, 0.01)
        depth_2 = self._cumulative_depth(bids, asks, midpoint, 0.02)
        depth_5 = self._cumulative_depth(bids, asks, midpoint, 0.05)

        # Walk-the-book slippage for buying (consuming asks)
        avg_fill, slippage = self._walk_the_book(asks, midpoint, intended_size_usd)
        sufficient = depth_1 >= intended_size_usd

        return OrderBookSnapshot(
            token_id=token_id,
            midpoint=midpoint,
            spread_cents=spread_cents,
            spread_bps=spread_bps,
            total_bid_size=total_bid_size,
            total_ask_size=total_ask_size,
            bid_ask_imbalance=imbalance,
            depth_at_1pct=depth_1,
            depth_at_2pct=depth_2,
            depth_at_5pct=depth_5,
            avg_fill_price=avg_fill,
            expected_slippage_cents=slippage,
            sufficient_liquidity=sufficient,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_levels=len(bids),
            ask_levels=len(asks),
        )

    def _cumulative_depth(
        self,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        midpoint: float,
        pct: float,
    ) -> float:
        """Sum USD volume within pct of midpoint on both sides."""
        threshold = midpoint * pct
        depth = 0.0
        for price, size in bids:
            if abs(price - midpoint) <= threshold:
                depth += price * size
        for price, size in asks:
            if abs(price - midpoint) <= threshold:
                depth += price * size
        return depth

    def _walk_the_book(
        self,
        asks: list[tuple[float, float]],
        midpoint: float,
        intended_size_usd: float,
    ) -> tuple[float, float]:
        """Simulate filling a buy order against ask levels.

        Returns (avg_fill_price, slippage_cents).
        """
        if not asks or intended_size_usd <= 0:
            return midpoint, 0.0

        remaining = intended_size_usd
        total_cost = 0.0
        total_shares = 0.0

        for price, size in asks:
            level_usd = price * size
            if remaining <= 0:
                break
            fill_usd = min(level_usd, remaining)
            shares = fill_usd / price if price > 0 else 0
            total_cost += fill_usd
            total_shares += shares
            remaining -= fill_usd

        if total_shares <= 0:
            return midpoint, 0.0

        avg_fill = total_cost / total_shares
        slippage = avg_fill - midpoint
        return avg_fill, max(0.0, slippage)

    def _recalc_slippage(
        self, snapshot: OrderBookSnapshot, intended_size_usd: float
    ) -> OrderBookSnapshot:
        """Return snapshot (slippage already computed; use as-is from cache)."""
        return snapshot

    def _empty_snapshot(self, token_id: str) -> OrderBookSnapshot:
        """Return an empty/neutral snapshot when book is unavailable."""
        return OrderBookSnapshot(
            token_id=token_id,
            midpoint=0.0,
            spread_cents=0.0,
            spread_bps=0.0,
            total_bid_size=0.0,
            total_ask_size=0.0,
            bid_ask_imbalance=0.0,
            depth_at_1pct=0.0,
            depth_at_2pct=0.0,
            depth_at_5pct=0.0,
            avg_fill_price=0.0,
            expected_slippage_cents=0.0,
            sufficient_liquidity=False,
        )
