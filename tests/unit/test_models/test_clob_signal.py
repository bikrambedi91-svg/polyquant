"""Tests for CLOBSignal model — Polymarket order book imbalance."""

import pytest
from tests.unit.test_models.conftest import make_default_params
from models.clob_signal import CLOBSignalModel


@pytest.fixture
def model():
    return CLOBSignalModel(make_default_params("CLOBSignal", "5m"))


@pytest.mark.asyncio
async def test_bid_heavy_imbalance_bullish(model):
    """Imbalance=1.5 (bids >> asks) → prob_up > 0.55."""
    book = {"total_bid_size": 15000, "total_ask_size": 10000, "recent_large_trades": []}
    out = await model.generate_signal("BTC", "5m", book_data=book)
    assert out.prob_up > 0.55
    assert out.confidence > 30
    assert any("bid_heavy" in d for d in out.key_drivers)


@pytest.mark.asyncio
async def test_ask_heavy_imbalance_bearish(model):
    """Imbalance=0.5 (asks >> bids) → prob_up < 0.45."""
    book = {"total_bid_size": 5000, "total_ask_size": 15000, "recent_large_trades": []}
    out = await model.generate_signal("BTC", "5m", book_data=book)
    assert out.prob_up < 0.45
    assert any("ask_heavy" in d for d in out.key_drivers)


@pytest.mark.asyncio
async def test_balanced_book(model):
    """Balanced book → neutral, prob near 0.5."""
    book = {"total_bid_size": 10000, "total_ask_size": 10000, "recent_large_trades": []}
    out = await model.generate_signal("BTC", "5m", book_data=book)
    assert 0.45 <= out.prob_up <= 0.55


@pytest.mark.asyncio
async def test_large_buy_trades_boost(model):
    """Recent large buy trades → additional bullish boost."""
    book = {
        "total_bid_size": 14000,
        "total_ask_size": 10000,
        "recent_large_trades": [
            {"size": 800, "side": "BUY"},
            {"size": 600, "side": "BUY"},
        ],
    }
    out = await model.generate_signal("BTC", "5m", book_data=book)
    assert out.prob_up >= 0.55


@pytest.mark.asyncio
async def test_4h_timeframe_returns_zero_confidence(model):
    """4h timeframe → confidence=0 (CLOB is noise on long horizons)."""
    book = {"total_bid_size": 20000, "total_ask_size": 10000, "recent_large_trades": []}
    out = await model.generate_signal("BTC", "4h", book_data=book)
    assert out.confidence == 0
    assert out.prob_up == 0.5


@pytest.mark.asyncio
async def test_no_book_data(model):
    """Missing book data → safe output."""
    out = await model.generate_signal("BTC", "5m")
    assert out.confidence == 0


@pytest.mark.asyncio
async def test_zero_sizes(model):
    """Zero bid/ask sizes → safe output."""
    book = {"total_bid_size": 0, "total_ask_size": 0, "recent_large_trades": []}
    out = await model.generate_signal("BTC", "5m", book_data=book)
    assert out.confidence == 0
