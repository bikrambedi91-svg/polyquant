"""Tests for market/orderbook.py — CLOB order book analysis."""

import pytest
from unittest.mock import MagicMock

from data.cache import cache
from market.orderbook import OrderBookAnalyzer, OrderBookSnapshot


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def _make_mock_client(bids=None, asks=None):
    """Create a mock ClobClient with a fake order book."""
    mock = MagicMock()
    mock.get_order_book.return_value = {
        "bids": bids or [],
        "asks": asks or [],
    }
    return mock


@pytest.mark.asyncio
async def test_basic_spread_and_midpoint():
    """Verify spread and midpoint from simple 2-level book."""
    bids = [{"price": "0.50", "size": "1000"}, {"price": "0.49", "size": "500"}]
    asks = [{"price": "0.52", "size": "800"}, {"price": "0.53", "size": "600"}]
    client = _make_mock_client(bids, asks)

    analyzer = OrderBookAnalyzer(clob_client=client)
    snap = await analyzer.analyze("TOKEN_1", intended_size_usd=100)

    assert snap.best_bid == 0.50
    assert snap.best_ask == 0.52
    assert snap.midpoint == pytest.approx(0.51, abs=0.001)
    assert snap.spread_cents == pytest.approx(0.02, abs=0.001)
    assert snap.bid_levels == 2
    assert snap.ask_levels == 2


@pytest.mark.asyncio
async def test_bid_ask_imbalance():
    """More bids than asks → imbalance > 1."""
    bids = [{"price": "0.50", "size": "2000"}]
    asks = [{"price": "0.52", "size": "1000"}]
    client = _make_mock_client(bids, asks)

    analyzer = OrderBookAnalyzer(clob_client=client)
    snap = await analyzer.analyze("TOKEN_2")

    assert snap.bid_ask_imbalance == pytest.approx(2.0)
    assert snap.total_bid_size == 2000
    assert snap.total_ask_size == 1000


@pytest.mark.asyncio
async def test_walk_the_book_slippage():
    """Walk-the-book: filling $200 across multiple ask levels."""
    bids = [{"price": "0.50", "size": "1000"}]
    asks = [
        {"price": "0.52", "size": "200"},   # 200 shares × $0.52 = $104
        {"price": "0.54", "size": "200"},   # 200 shares × $0.54 = $108
        {"price": "0.56", "size": "200"},   # 200 shares × $0.56 = $112
    ]
    client = _make_mock_client(bids, asks)

    analyzer = OrderBookAnalyzer(clob_client=client)
    snap = await analyzer.analyze("TOKEN_3", intended_size_usd=200)

    # $200 fills: all of level 1 ($104), then ~$96 of level 2
    midpoint = (0.50 + 0.52) / 2  # 0.51
    assert snap.avg_fill_price > midpoint
    assert snap.expected_slippage_cents > 0


@pytest.mark.asyncio
async def test_insufficient_liquidity_flag():
    """Depth < intended size → insufficient_liquidity."""
    bids = [{"price": "0.50", "size": "10"}]   # tiny size
    asks = [{"price": "0.52", "size": "10"}]
    client = _make_mock_client(bids, asks)

    analyzer = OrderBookAnalyzer(clob_client=client)
    snap = await analyzer.analyze("TOKEN_4", intended_size_usd=1000)

    assert snap.sufficient_liquidity is False


@pytest.mark.asyncio
async def test_sufficient_liquidity():
    """Lots of depth → sufficient_liquidity=True."""
    bids = [{"price": "0.50", "size": "50000"}]
    asks = [{"price": "0.51", "size": "50000"}]
    client = _make_mock_client(bids, asks)

    analyzer = OrderBookAnalyzer(clob_client=client)
    snap = await analyzer.analyze("TOKEN_5", intended_size_usd=100)

    assert snap.sufficient_liquidity is True


@pytest.mark.asyncio
async def test_empty_book_returns_safe():
    """Empty order book → zero values, not sufficient."""
    client = _make_mock_client(bids=[], asks=[])

    analyzer = OrderBookAnalyzer(clob_client=client)
    snap = await analyzer.analyze("TOKEN_6")

    assert snap.midpoint == 0.0
    assert snap.sufficient_liquidity is False
    assert snap.spread_cents == 0.0


@pytest.mark.asyncio
async def test_depth_at_percentage():
    """Cumulative depth within 1%/2%/5% of midpoint."""
    # Midpoint will be 0.505
    # 1% of 0.505 = 0.00505 → only prices within [0.49995, 0.51005]
    bids = [
        {"price": "0.50", "size": "1000"},   # within 1%
        {"price": "0.48", "size": "500"},     # outside 1% (diff = 0.025)
    ]
    asks = [
        {"price": "0.51", "size": "800"},     # within 1%
        {"price": "0.55", "size": "600"},     # outside 1%
    ]
    client = _make_mock_client(bids, asks)

    analyzer = OrderBookAnalyzer(clob_client=client)
    snap = await analyzer.analyze("TOKEN_7")

    # Depth at 1%: bid level 0.50 (1000*0.50=500) + ask level 0.51 (800*0.51=408) = ~908
    assert snap.depth_at_1pct > 0
    # Depth at 5% should be larger (includes more levels)
    assert snap.depth_at_5pct >= snap.depth_at_1pct


@pytest.mark.asyncio
async def test_cache_hit():
    """Second call with same token_id should hit cache."""
    bids = [{"price": "0.50", "size": "1000"}]
    asks = [{"price": "0.52", "size": "800"}]
    client = _make_mock_client(bids, asks)

    analyzer = OrderBookAnalyzer(clob_client=client)
    snap1 = await analyzer.analyze("TOKEN_CACHED")
    snap2 = await analyzer.analyze("TOKEN_CACHED")

    # Client should only be called once (second call from cache)
    assert client.get_order_book.call_count == 1
    assert snap1.midpoint == snap2.midpoint


@pytest.mark.asyncio
async def test_api_error_returns_empty():
    """If CLOB client raises, return empty snapshot."""
    client = MagicMock()
    client.get_order_book.side_effect = Exception("CLOB down")

    analyzer = OrderBookAnalyzer(clob_client=client)
    snap = await analyzer.analyze("TOKEN_ERR")

    assert snap.midpoint == 0.0
    assert snap.sufficient_liquidity is False
