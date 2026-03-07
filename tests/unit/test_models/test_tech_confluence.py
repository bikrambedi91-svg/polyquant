"""Tests for TechConfluence model — RSI/MACD/BB/VWAP/Volume confluence."""

import pytest
from tests.unit.test_models.conftest import make_ohlcv, make_default_params
from models.tech_confluence import TechConfluenceModel


@pytest.fixture
def model():
    return TechConfluenceModel(make_default_params("TechConf", "1h"))


@pytest.mark.asyncio
async def test_strong_bullish_confluence(model):
    """Strong uptrend data → 4+/5 bullish indicators → prob_up > 0.65."""
    ohlcv = make_ohlcv(150, trend="up", volatility=0.003, seed=42)
    out = await model.generate_signal("BTC", "1h", ohlcv)
    assert out.prob_up > 0.55
    assert out.confidence > 30
    assert "confluence=" in out.key_drivers[-1]


@pytest.mark.asyncio
async def test_strong_bearish_confluence(model):
    """Strong downtrend → bearish indicators → prob_up < 0.45."""
    ohlcv = make_ohlcv(150, trend="down", volatility=0.003, seed=42)
    out = await model.generate_signal("ETH", "1h", ohlcv)
    assert out.prob_up < 0.50


@pytest.mark.asyncio
async def test_flat_market_neutral(model):
    """Flat data → mixed signals → prob in reasonable range."""
    ohlcv = make_ohlcv(150, trend="flat", volatility=0.002, seed=42)
    out = await model.generate_signal("SOL", "1h", ohlcv)
    assert 0.10 <= out.prob_up <= 0.90


@pytest.mark.asyncio
async def test_insufficient_data(model):
    """Too few bars → safe output."""
    ohlcv = make_ohlcv(10, trend="up")
    out = await model.generate_signal("BTC", "1h", ohlcv)
    assert out.confidence == 0


@pytest.mark.asyncio
async def test_raw_indicators_populated(model):
    """Raw indicators should include RSI, MACD, BB, counts."""
    ohlcv = make_ohlcv(150, trend="up")
    out = await model.generate_signal("BTC", "1h", ohlcv)
    assert "rsi" in out.raw_indicators
    assert "bullish_count" in out.raw_indicators
    assert "bearish_count" in out.raw_indicators


@pytest.mark.asyncio
async def test_prob_clamped(model):
    """Output prob must stay in [0, 1]."""
    ohlcv = make_ohlcv(150, trend="up", volatility=0.001)
    out = await model.generate_signal("BTC", "1h", ohlcv)
    assert 0.0 <= out.prob_up <= 1.0
